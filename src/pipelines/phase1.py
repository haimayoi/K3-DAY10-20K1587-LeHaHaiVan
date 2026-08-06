from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, TypeVar

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import EvaluationBundle, evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import PaperRecord, fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


REQUIRED_CLEAN_COLUMNS = {
    "paper_id",
    "title",
    "summary",
    "published",
    "age_days",
    "authors_joined",
    "categories_joined",
    "abs_url",
    "pdf_url",
    "text_for_embedding",
}
CRITICAL_NON_EMPTY_COLUMNS = ("paper_id", "title", "text_for_embedding")

T = TypeVar("T")


class Phase1Blocker(RuntimeError):
    """A pipeline dependency or data contract is not ready for integration."""


def _run_stage(stage: str, action: Callable[[], T]) -> T:
    print(f"[phase1] {stage}...")
    try:
        result = action()
    except NotImplementedError as exc:
        raise Phase1Blocker(
            f"Checkpoint 1 blocker at '{stage}': {exc}. "
            "Complete the owning module before this stage can run."
        ) from exc
    print(f"[phase1] {stage}: done")
    return result


def _load_or_fetch_raw_records(settings: Settings) -> list[PaperRecord]:
    raw_path = settings.paths.raw_records_json
    if raw_path.exists() and not settings.refresh_source:
        print(f"[phase1] Reusing raw snapshot: {raw_path}")
        return load_raw_records(raw_path)
    return fetch_source_records(settings)


def _empty_row_count(df: pd.DataFrame, column: str) -> int:
    values = df[column]
    return int((values.isna() | values.astype(str).str.strip().eq("")).sum())


def _review_clean_contract(raw_count: int, clean_df: pd.DataFrame) -> dict[str, Any]:
    clean_count = len(clean_df)
    missing_columns = sorted(REQUIRED_CLEAN_COLUMNS - set(clean_df.columns))
    evidence: dict[str, Any] = {
        "raw_count": raw_count,
        "clean_count": clean_count,
        "dropped_count": raw_count - clean_count,
        "retention_rate": round(clean_count / raw_count, 4) if raw_count else 0.0,
        "missing_required_columns": missing_columns,
    }

    blockers: list[str] = []
    if raw_count == 0:
        blockers.append("raw dataset is empty")
    if clean_count == 0:
        blockers.append("clean dataset is empty")
    if clean_count > raw_count:
        blockers.append("clean count is greater than raw count")
    if missing_columns:
        blockers.append("clean schema is missing downstream-required columns")

    if not missing_columns:
        empty_counts = {
            column: _empty_row_count(clean_df, column)
            for column in CRITICAL_NON_EMPTY_COLUMNS
        }
        duplicate_paper_ids = int(clean_df["paper_id"].duplicated(keep=False).sum())
        evidence["critical_empty_counts"] = empty_counts
        evidence["duplicate_paper_id_rows"] = duplicate_paper_ids

        if any(empty_counts.values()):
            blockers.append("critical clean fields contain empty values")
        if duplicate_paper_ids:
            blockers.append("paper_id is not unique after cleaning")

    print(f"[phase1] raw -> clean evidence: {json.dumps(evidence, ensure_ascii=True)}")
    if blockers:
        raise Phase1Blocker(
            "Clean schema/count gate failed; index and test set were not started. "
            f"Blockers: {blockers}. Evidence: {json.dumps(evidence, ensure_ascii=True)}"
        )
    return evidence


def _write_clean_artifacts(clean_df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    write_csv(clean_df, csv_path)
    records = json.loads(clean_df.to_json(orient="records", date_format="iso"))
    write_json(json_path, records)


def _load_or_build_test_set(settings: Settings, clean_df: pd.DataFrame) -> list[dict[str, Any]]:
    test_set_path = settings.paths.eval_testset
    if test_set_path.exists() and not settings.refresh_test_set:
        return read_json(test_set_path)
    return build_test_set(clean_df, test_set_path)


def main() -> None:
    """Run the phase-1 baseline in dependency order."""
    settings = load_settings()

    raw_records = _run_stage("raw", lambda: _load_or_fetch_raw_records(settings))
    clean_df = _run_stage(
        "clean",
        lambda: build_clean_dataframe(raw_records, run_date=now_utc()),
    )

    count_evidence = _review_clean_contract(len(raw_records), clean_df)
    _run_stage(
        "write clean artifacts",
        lambda: _write_clean_artifacts(
            clean_df,
            settings.paths.clean_csv,
            settings.paths.clean_json,
        ),
    )

    index = _run_stage(
        "index",
        lambda: LocalEmbeddingIndex.build(
            clean_df,
            settings,
            embeddings_output_path=settings.paths.embeddings_json,
        ),
    )
    test_set = _run_stage(
        "test set",
        lambda: _load_or_build_test_set(settings, clean_df),
    )
    if not test_set:
        raise Phase1Blocker("Test set is empty; evaluation was not started.")

    evaluation: EvaluationBundle = _run_stage(
        "evaluate",
        lambda: evaluate_pipeline(
            settings,
            index,
            settings.paths.eval_testset,
            settings.paths.baseline_metrics,
            settings.paths.baseline_answers,
        ),
    )
    quality = _run_stage(
        "quality",
        lambda: run_data_quality_checks(clean_df, settings, report_name="baseline"),
    )
    freshness = _run_stage(
        "freshness",
        lambda: build_freshness_report(
            clean_df,
            settings,
            settings.paths.freshness_report,
        ),
    )

    source_summary = {
        "source": settings.source_api,
        "query": settings.source_query,
        **count_evidence,
    }
    _run_stage(
        "report",
        lambda: generate_phase1_report(
            settings.paths.baseline_report,
            source_summary,
            evaluation.summary,
            quality,
            freshness,
        ),
    )

    print(f"[phase1] Baseline report: {settings.paths.baseline_report}")
