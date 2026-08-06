from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, time, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import PaperRecord, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import METRIC_NAMES, generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


class CorruptionFlowBlocker(RuntimeError):
    """The baseline, corrupted, or repaired-data contract is not ready."""


def _require_baseline(settings: Settings) -> list[Path]:
    required = [
        settings.paths.raw_records_json,
        settings.paths.clean_csv,
        settings.paths.clean_json,
        settings.paths.embeddings_json,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.baseline_answers,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise CorruptionFlowBlocker(
            f"Baseline is incomplete; run phase1 before corruption. Missing: {missing}"
        )
    return required


def _require_corrupted(settings: Settings) -> list[Path]:
    corrupted_freshness_path = settings.paths.quality_dir / "corrupted-freshness.json"
    required = [
        settings.paths.corrupted_clean_csv,
        settings.paths.corrupted_clean_json,
        settings.paths.corrupted_embeddings_json,
        settings.paths.corruption_log,
        settings.paths.corrupted_metrics,
        settings.paths.corrupted_answers,
        settings.paths.quality_dir / "corrupted.json",
        corrupted_freshness_path,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise CorruptionFlowBlocker(
            "Corrupted artifacts are incomplete; run checkpoint 5 before comparison. "
            f"Missing: {missing}"
        )
    return required


def _assert_isolated_outputs(settings: Settings) -> None:
    path_groups = [
        (
            settings.paths.clean_csv,
            settings.paths.corrupted_clean_csv,
            settings.paths.repaired_clean_csv,
        ),
        (
            settings.paths.clean_json,
            settings.paths.corrupted_clean_json,
            settings.paths.repaired_clean_json,
        ),
        (
            settings.paths.embeddings_json,
            settings.paths.corrupted_embeddings_json,
            settings.paths.repaired_embeddings_json,
        ),
        (
            settings.paths.baseline_metrics,
            settings.paths.corrupted_metrics,
            settings.paths.repaired_metrics,
        ),
        (
            settings.paths.baseline_answers,
            settings.paths.corrupted_answers,
            settings.paths.repaired_answers,
        ),
    ]
    collisions = []
    for group in path_groups:
        resolved = [path.resolve() for path in group]
        if len(set(resolved)) != len(resolved):
            collisions.extend(str(path) for path in group)
    if collisions:
        raise CorruptionFlowBlocker(
            f"Baseline/corrupted/repaired outputs must use separate paths: {sorted(set(collisions))}"
        )
    collection_names = {
        settings.baseline_collection_name,
        settings.corrupted_collection_name,
        settings.repaired_collection_name,
    }
    if len(collection_names) != 3:
        raise CorruptionFlowBlocker(
            "Baseline/corrupted/repaired Chroma collection names must all differ."
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_dataframe(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    write_csv(df, csv_path)
    records = json.loads(df.to_json(orient="records", date_format="iso"))
    write_json(json_path, records)


def _normalize_managed_manifest(
    settings: Settings,
    manifest_path: Path,
    expected_collection_name: str,
) -> None:
    if not manifest_path.exists():
        return

    payload = read_json(manifest_path)
    collection_name = payload.get("collection_name")
    if collection_name != expected_collection_name:
        raise CorruptionFlowBlocker(
            f"Manifest {manifest_path} points to '{collection_name}', expected '{expected_collection_name}'."
        )

    expected_persist_path = LocalEmbeddingIndex._manifest_persist_path(
        settings,
        settings.paths.chroma_dir,
    )
    if payload.get("persist_path") != expected_persist_path:
        payload["persist_path"] = expected_persist_path
        write_json(manifest_path, payload)
        print(f"[corruption] Normalized manifest persist_path: {manifest_path}")


def _normalize_managed_manifests(settings: Settings) -> None:
    _normalize_managed_manifest(
        settings,
        settings.paths.embeddings_json,
        settings.baseline_collection_name,
    )
    _normalize_managed_manifest(
        settings,
        settings.paths.corrupted_embeddings_json,
        settings.corrupted_collection_name,
    )
    _normalize_managed_manifest(
        settings,
        settings.paths.repaired_embeddings_json,
        settings.repaired_collection_name,
    )


def _collection_count(settings: Settings, collection_name: str) -> int:
    database_path = (settings.paths.chroma_dir / "chroma.sqlite3").resolve()
    if not database_path.exists():
        raise CorruptionFlowBlocker(
            f"Chroma database is unavailable: {database_path}"
        )
    try:
        connection = sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=ro",
            uri=True,
        )
        row = connection.execute(
            """
            SELECT COUNT(embeddings.id)
            FROM collections
            JOIN segments ON segments.collection = collections.id
            JOIN embeddings ON embeddings.segment_id = segments.id
            WHERE collections.name = ?
            """,
            (collection_name,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise CorruptionFlowBlocker(
            f"Cannot inspect Chroma collection '{collection_name}': {exc}"
        ) from exc
    finally:
        if "connection" in locals():
            connection.close()
    if row is None or int(row[0]) == 0:
        raise CorruptionFlowBlocker(
            f"Required Chroma collection '{collection_name}' is empty or unavailable."
        )
    return int(row[0])


def _infer_clean_run_datetime(clean_df: pd.DataFrame) -> datetime:
    inferred_dates = []
    for _, row in clean_df.iterrows():
        published = pd.to_datetime(row.get("published"), errors="coerce")
        age_days = pd.to_numeric(row.get("age_days"), errors="coerce")
        if pd.isna(published) or pd.isna(age_days):
            continue
        inferred_dates.append(published.date() + timedelta(days=int(age_days)))

    if not inferred_dates:
        return datetime.now(UTC)

    run_date = Counter(inferred_dates).most_common(1)[0][0]
    return datetime.combine(run_date, time.min, tzinfo=UTC)


def _raw_records_by_id(raw_records: list[PaperRecord]) -> dict[str, PaperRecord]:
    return {record.paper_id: record for record in raw_records}


def _frame_counts_by_id(df: pd.DataFrame) -> Counter[str]:
    if "paper_id" not in df.columns:
        return Counter()
    return Counter(df["paper_id"].fillna("").astype(str))


def _frame_records_by_id(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if "paper_id" not in df.columns:
        return {}
    return {
        str(row["paper_id"]): row
        for row in df.to_dict(orient="records")
        if str(row.get("paper_id", "")).strip()
    }


def _build_repair_lineage(
    raw_records: list[PaperRecord],
    corrupted_df: pd.DataFrame,
    repaired_df: pd.DataFrame,
    corruption_log: dict[str, Any],
) -> dict[str, Any]:
    raw_by_id = _raw_records_by_id(raw_records)
    corrupted_counts = _frame_counts_by_id(corrupted_df)
    repaired_counts = _frame_counts_by_id(repaired_df)
    repaired_by_id = _frame_records_by_id(repaired_df)
    events_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for event in corruption_log.get("events", []):
        event_info = {
            "corruption_type": event.get("corruption_type"),
            "parameters": event.get("parameters", {}),
        }
        for paper_id in event.get("record_ids", []):
            events_by_id[str(paper_id)].append(event_info)

    evidence = []
    blockers = []
    for paper_id, events in sorted(events_by_id.items()):
        raw_record = raw_by_id.get(paper_id)
        repaired_record = repaired_by_id.get(paper_id)
        checks: dict[str, bool] = {
            "present_in_raw": raw_record is not None,
            "present_in_repaired": repaired_counts[paper_id] >= 1,
            "unique_in_repaired": repaired_counts[paper_id] == 1,
        }

        for event in events:
            corruption_type = event["corruption_type"]
            parameters = event["parameters"]
            if raw_record is None or repaired_record is None:
                checks[f"{corruption_type}_restored"] = False
                continue

            if corruption_type == "blank_summary":
                checks["blank_summary_restored"] = bool(str(repaired_record.get("summary", "")).strip())
            elif corruption_type == "add_summary_noise":
                prefix = str(parameters.get("prefix", ""))
                checks["summary_noise_removed"] = not str(repaired_record.get("summary", "")).startswith(prefix)
            elif corruption_type == "truncate_title":
                checks["title_restored"] = repaired_record.get("title") == raw_record.title
            elif corruption_type == "make_publication_stale":
                checks["published_restored"] = repaired_record.get("published") == raw_record.published
            elif corruption_type == "drop_latest_records":
                checks["dropped_record_restored"] = repaired_counts[paper_id] >= 1
            elif corruption_type == "add_duplicate_rows":
                checks["duplicate_removed"] = repaired_counts[paper_id] == 1

        failed_checks = [name for name, passed in checks.items() if not passed]
        if failed_checks:
            blockers.append({"paper_id": paper_id, "failed_checks": failed_checks})

        evidence.append(
            {
                "paper_id": paper_id,
                "corruption_types": [event["corruption_type"] for event in events],
                "raw_title": raw_record.title if raw_record else None,
                "raw_published": raw_record.published if raw_record else None,
                "corrupted_count": corrupted_counts[paper_id],
                "repaired_count": repaired_counts[paper_id],
                "checks": checks,
            }
        )

    return {
        "schema_version": 1,
        "raw_count": len(raw_records),
        "corrupted_count": len(corrupted_df),
        "repaired_count": len(repaired_df),
        "records": evidence,
        "passed": not blockers,
        "blockers": blockers,
    }


def _assert_report_matches_artifacts(
    settings: Settings,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
) -> None:
    report_path = settings.paths.comparison_report
    if not report_path.exists() or report_path.stat().st_size == 0:
        raise CorruptionFlowBlocker(f"Comparison report was not created: {report_path}")

    report_text = report_path.read_text(encoding="utf-8")
    required_terms = ["Baseline", "Corrupted", "Repaired", *METRIC_NAMES]
    missing_terms = [term for term in required_terms if term not in report_text]
    if missing_terms:
        raise CorruptionFlowBlocker(
            f"Comparison report is missing required sections/metrics: {missing_terms}"
        )

    for metrics_path, metrics in [
        (settings.paths.baseline_metrics, baseline_metrics),
        (settings.paths.corrupted_metrics, corrupted_metrics),
        (settings.paths.repaired_metrics, repaired_metrics),
    ]:
        missing_metrics = [name for name in METRIC_NAMES if name not in metrics]
        if missing_metrics:
            raise CorruptionFlowBlocker(
                f"Metrics artifact {metrics_path} is missing keys: {missing_metrics}"
            )


def _tracked_files(settings: Settings) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=settings.paths.project_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        settings.paths.project_dir / line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def _assert_no_tracked_secrets_or_hardcoded_paths(settings: Settings) -> dict[str, Any]:
    tracked_files = _tracked_files(settings)
    tracked_env_files = [
        str(path.relative_to(settings.paths.project_dir))
        for path in tracked_files
        if path.name == ".env"
    ]
    if tracked_env_files:
        raise CorruptionFlowBlocker(f"Secret env files are tracked by Git: {tracked_env_files}")

    secret_assignment_pattern = re.compile(
        r"(?m)^\s*(?:export\s+)?"
        r"(OPENAI_API_KEY|GOOGLE_API_KEY|ANTHROPIC_API_KEY|OPENROUTER_API_KEY)\s*=\s*"
        r"(?!your_|example|changeme|<|$)[^\s#]+"
    )
    secret_token_pattern = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}")
    absolute_path_pattern = re.compile(r"[A-Za-z]:\\\\")
    flagged_secrets = []
    flagged_paths = []

    for path in tracked_files:
        if path.suffix.lower() not in {".py", ".json", ".md", ".txt", ".toml", ".yaml", ".yml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        relative_path = str(path.relative_to(settings.paths.project_dir))
        if secret_assignment_pattern.search(text) or secret_token_pattern.search(text):
            flagged_secrets.append(relative_path)
        if absolute_path_pattern.search(text):
            flagged_paths.append(relative_path)

    if flagged_secrets:
        raise CorruptionFlowBlocker(f"Potential tracked secrets found: {flagged_secrets}")
    if flagged_paths:
        raise CorruptionFlowBlocker(f"Hard-coded absolute paths found in tracked files: {flagged_paths}")

    return {
        "tracked_env_files": tracked_env_files,
        "potential_secret_files": flagged_secrets,
        "hardcoded_absolute_path_files": flagged_paths,
        "tracked_files_scanned": len(tracked_files),
    }


def main() -> None:
    """Build corrupted/repaired branches and compare them against baseline."""
    settings = load_settings()
    _assert_isolated_outputs(settings)
    _normalize_managed_manifests(settings)
    baseline_files = _require_baseline(settings)
    baseline_hashes = {path: _sha256(path) for path in baseline_files}
    baseline_collection_count = _collection_count(settings, settings.baseline_collection_name)

    print("[corruption] Loading baseline clean dataset...")
    clean_df = pd.read_csv(settings.paths.clean_csv)
    baseline_metrics = read_json(settings.paths.baseline_metrics)
    test_set = read_json(settings.paths.eval_testset)
    if len(clean_df) != baseline_collection_count:
        raise CorruptionFlowBlocker(
            "Baseline clean/index count mismatch. "
            f"clean_count={len(clean_df)}, collection_count={baseline_collection_count}"
        )
    if not baseline_metrics or not test_set:
        raise CorruptionFlowBlocker("Baseline metrics and fixed test set must be non-empty.")

    print("[corruption] Applying deterministic corruption scenarios...")
    corrupted_df = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)
    _write_dataframe(
        corrupted_df,
        settings.paths.corrupted_clean_csv,
        settings.paths.corrupted_clean_json,
    )

    print(f"[corruption] Building collection '{settings.corrupted_collection_name}'...")
    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df,
        settings,
        embeddings_output_path=settings.paths.corrupted_embeddings_json,
    )
    if corrupted_index.collection_name != settings.corrupted_collection_name:
        raise CorruptionFlowBlocker(
            "Corrupted index used the wrong collection: "
            f"{corrupted_index.collection_name}"
        )
    if corrupted_index.collection.count() != len(corrupted_df):
        raise CorruptionFlowBlocker(
            "Corrupted clean/index count mismatch. "
            f"clean_count={len(corrupted_df)}, collection_count={corrupted_index.collection.count()}"
        )

    print("[corruption] Evaluating with the fixed baseline test set...")
    evaluation = evaluate_pipeline(
        settings,
        corrupted_index,
        settings.paths.eval_testset,
        settings.paths.corrupted_metrics,
        settings.paths.corrupted_answers,
    )
    quality = run_data_quality_checks(corrupted_df, settings, report_name="corrupted")
    corrupted_freshness_path = settings.paths.quality_dir / "corrupted-freshness.json"
    freshness = build_freshness_report(
        corrupted_df,
        settings,
        corrupted_freshness_path,
    )

    _normalize_managed_manifest(
        settings,
        settings.paths.corrupted_embeddings_json,
        settings.corrupted_collection_name,
    )
    corrupted_files = _require_corrupted(settings)
    baseline_and_corrupted_files = baseline_files + corrupted_files
    baseline_and_corrupted_hashes = {
        path: _sha256(path)
        for path in baseline_and_corrupted_files
    }

    print("[corruption] Re-running repair clean from raw snapshot...")
    raw_records = load_raw_records(settings.paths.raw_records_json)
    repair_run_date = _infer_clean_run_datetime(clean_df)
    repaired_df = build_clean_dataframe(raw_records, run_date=repair_run_date)
    _write_dataframe(
        repaired_df,
        settings.paths.repaired_clean_csv,
        settings.paths.repaired_clean_json,
    )

    lineage = _build_repair_lineage(
        raw_records,
        corrupted_df,
        repaired_df,
        read_json(settings.paths.corruption_log),
    )
    repair_lineage_path = settings.paths.repaired_metrics.parent / "repair_lineage.json"
    write_json(repair_lineage_path, lineage)
    if not lineage["passed"]:
        raise CorruptionFlowBlocker(
            "Repaired data does not restore every corrupted record from raw evidence. "
            f"See {repair_lineage_path}."
        )

    print(f"[corruption] Building collection '{settings.repaired_collection_name}'...")
    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        settings,
        embeddings_output_path=settings.paths.repaired_embeddings_json,
    )
    if repaired_index.collection_name != settings.repaired_collection_name:
        raise CorruptionFlowBlocker(
            "Repaired index used the wrong collection: "
            f"{repaired_index.collection_name}"
        )
    if repaired_index.collection.count() != len(repaired_df):
        raise CorruptionFlowBlocker(
            "Repaired clean/index count mismatch. "
            f"clean_count={len(repaired_df)}, collection_count={repaired_index.collection.count()}"
        )

    print("[corruption] Evaluating repaired with the fixed baseline test set...")
    repaired_evaluation = evaluate_pipeline(
        settings,
        repaired_index,
        settings.paths.eval_testset,
        settings.paths.repaired_metrics,
        settings.paths.repaired_answers,
    )
    repaired_quality = run_data_quality_checks(repaired_df, settings, report_name="repaired")
    repaired_freshness_path = settings.paths.quality_dir / "repaired-freshness.json"
    repaired_freshness = build_freshness_report(
        repaired_df,
        settings,
        repaired_freshness_path,
    )

    _normalize_managed_manifest(
        settings,
        settings.paths.repaired_embeddings_json,
        settings.repaired_collection_name,
    )

    baseline_metrics = read_json(settings.paths.baseline_metrics)
    corrupted_metrics = read_json(settings.paths.corrupted_metrics)
    repaired_metrics = read_json(settings.paths.repaired_metrics)
    corrupted_quality = read_json(settings.paths.quality_dir / "corrupted.json")
    corrupted_freshness = read_json(corrupted_freshness_path)
    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics,
        corrupted_metrics,
        repaired_metrics,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
    )
    _assert_report_matches_artifacts(
        settings,
        baseline_metrics,
        corrupted_metrics,
        repaired_metrics,
    )

    changed_baseline_files = [
        str(path) for path, before_hash in baseline_hashes.items() if _sha256(path) != before_hash
    ]
    if changed_baseline_files:
        raise CorruptionFlowBlocker(
            f"Corruption flow overwrote baseline artifacts: {changed_baseline_files}"
        )
    after_baseline_count = _collection_count(settings, settings.baseline_collection_name)
    if after_baseline_count != baseline_collection_count:
        raise CorruptionFlowBlocker(
            "Baseline Chroma collection changed during corruption. "
            f"before={baseline_collection_count}, after={after_baseline_count}"
        )
    changed_baseline_or_corrupted_files = [
        str(path)
        for path, before_hash in baseline_and_corrupted_hashes.items()
        if _sha256(path) != before_hash
    ]
    if changed_baseline_or_corrupted_files:
        raise CorruptionFlowBlocker(
            "Repair/comparison flow overwrote baseline or corrupted artifacts: "
            f"{changed_baseline_or_corrupted_files}"
        )

    repaired_collection_count = _collection_count(settings, settings.repaired_collection_name)
    checklist = {
        "repaired_metrics_exists": settings.paths.repaired_metrics.exists(),
        "comparison_report_exists": settings.paths.comparison_report.exists(),
        "baseline_collection_rows": after_baseline_count,
        "corrupted_collection_rows": _collection_count(settings, settings.corrupted_collection_name),
        "repaired_collection_rows": repaired_collection_count,
        "report_path": str(settings.paths.comparison_report.relative_to(settings.paths.project_dir)),
        "lineage_path": str(repair_lineage_path.relative_to(settings.paths.project_dir)),
        "secret_and_path_check": _assert_no_tracked_secrets_or_hardcoded_paths(settings),
    }
    checklist_path = settings.paths.repaired_metrics.parent / "cp6_checklist.json"
    write_json(checklist_path, checklist)

    summary: dict[str, Any] = {
        "baseline_rows": len(clean_df),
        "corrupted_rows": len(corrupted_df),
        "repaired_rows": len(repaired_df),
        "baseline_collection_rows": baseline_collection_count,
        "corrupted_collection_rows": corrupted_index.collection.count(),
        "repaired_collection_rows": repaired_collection_count,
        "fixed_test_set_samples": len(test_set),
        "metrics": evaluation.summary,
        "quality_passed": quality["passed"],
        "freshness_passed": freshness["is_fresh"],
        "repaired_metrics": repaired_evaluation.summary,
        "repaired_quality_passed": repaired_quality["passed"],
        "repaired_freshness_passed": repaired_freshness["is_fresh"],
        "comparison_report": str(settings.paths.comparison_report),
    }
    print(f"[corruption] Complete: {json.dumps(summary, ensure_ascii=True)}")
