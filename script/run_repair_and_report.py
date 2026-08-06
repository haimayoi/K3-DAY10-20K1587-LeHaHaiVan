from __future__ import annotations

import json

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def _write_repaired_artifacts(clean_df, settings) -> None:
    """Persist repair output rebuilt from the original raw-record snapshot."""
    write_csv(clean_df, settings.paths.repaired_clean_csv)
    write_json(
        settings.paths.repaired_clean_json,
        json.loads(clean_df.to_json(orient="records", date_format="iso")),
    )


def main() -> None:
    """Complete CP6: repair from raw, evaluate, and write the comparison report."""
    settings = load_settings()
    required = [
        settings.paths.raw_records_json,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.corrupted_metrics,
        settings.paths.quality_dir / "baseline.json",
        settings.paths.quality_dir / "corrupted.json",
        settings.paths.quality_dir / "corrupted-freshness.json",
        settings.paths.freshness_report,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"Cannot complete repair comparison; missing artifacts: {missing}")
    raw_records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(raw_records, run_date=now_utc())
    if repaired_df.empty:
        raise RuntimeError("Repair produced no clean records from the raw snapshot.")
    _write_repaired_artifacts(repaired_df, settings)
    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        settings,
        embeddings_output_path=settings.paths.repaired_embeddings_json,
    )
    if repaired_index.collection_name != settings.repaired_collection_name:
        raise RuntimeError("Repair used an unexpected Chroma collection.")
    repaired_evaluation = evaluate_pipeline(
        settings,
        repaired_index,
        settings.paths.eval_testset,
        settings.paths.repaired_metrics,
        settings.paths.repaired_answers,
    )
    repaired_quality = run_data_quality_checks(repaired_df, settings, report_name="repaired")
    repaired_freshness = build_freshness_report(
        repaired_df,
        settings,
        settings.paths.quality_dir / "repaired-freshness.json",
    )
    generate_corruption_report(
        settings.paths.comparison_report,
        read_json(settings.paths.baseline_metrics),
        read_json(settings.paths.corrupted_metrics),
        repaired_evaluation.summary,
        read_json(settings.paths.quality_dir / "corrupted.json"),
        repaired_quality,
        read_json(settings.paths.quality_dir / "corrupted-freshness.json"),
        repaired_freshness,
        baseline_quality=read_json(settings.paths.quality_dir / "baseline.json"),
        baseline_freshness=read_json(settings.paths.freshness_report),
    )
    print(f"[repair] Repaired {len(repaired_df)} records and wrote {settings.paths.comparison_report}")


if __name__ == "__main__":
    main()
