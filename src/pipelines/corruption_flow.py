from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.corruption import corrupt_clean_dataframe
from observability.quality import build_freshness_report, run_data_quality_checks
from retrieval.index import LocalEmbeddingIndex


class CorruptionFlowBlocker(RuntimeError):
    """The baseline or corrupted-data contract is not ready."""


def _require_baseline(settings: Settings) -> list[Path]:
    required = [
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


def _assert_isolated_outputs(settings: Settings) -> None:
    path_pairs = [
        (settings.paths.clean_csv, settings.paths.corrupted_clean_csv),
        (settings.paths.clean_json, settings.paths.corrupted_clean_json),
        (settings.paths.embeddings_json, settings.paths.corrupted_embeddings_json),
        (settings.paths.baseline_metrics, settings.paths.corrupted_metrics),
        (settings.paths.baseline_answers, settings.paths.corrupted_answers),
    ]
    collisions = [str(baseline) for baseline, corrupted in path_pairs if baseline.resolve() == corrupted.resolve()]
    if collisions:
        raise CorruptionFlowBlocker(f"Corrupted outputs collide with baseline paths: {collisions}")
    if settings.baseline_collection_name == settings.corrupted_collection_name:
        raise CorruptionFlowBlocker("Baseline and corrupted Chroma collection names must differ.")


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


def main() -> None:
    """Build and evaluate the isolated corrupted branch for checkpoint 5."""
    settings = load_settings()
    _assert_isolated_outputs(settings)
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

    summary: dict[str, Any] = {
        "baseline_rows": len(clean_df),
        "corrupted_rows": len(corrupted_df),
        "baseline_collection_rows": baseline_collection_count,
        "corrupted_collection_rows": corrupted_index.collection.count(),
        "fixed_test_set_samples": len(test_set),
        "metrics": evaluation.summary,
        "quality_passed": quality["passed"],
        "freshness_passed": freshness["is_fresh"],
    }
    print(f"[corruption] Complete: {json.dumps(summary, ensure_ascii=True)}")
