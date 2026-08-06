from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils import write_text


METRIC_NAMES = ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score")


def _display(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, bool):
        return "Pass" if value else "Fail"
    return str(value)


def _markdown_table(rows: list[tuple[str, Any]]) -> str:
    lines = ["| Item | Value |", "| --- | --- |"]
    lines.extend(f"| {key} | {_display(value)} |" for key, value in rows)
    return "\n".join(lines)


def generate_phase1_report(
    report_path: Path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a baseline report from the artifacts produced by the pipeline."""
    quality_checks = quality.get("checks", {})
    quality_rows = [(name, "Pass" if check.get("passed") else "Fail") for name, check in quality_checks.items()]
    sections = [
        "# Phase 1 Baseline Report",
        "## Source",
        _markdown_table(list(source_summary.items())),
        "## Evaluation Metrics",
        _markdown_table([(name, metrics.get(name)) for name in METRIC_NAMES] + [("samples", metrics.get("samples"))]),
        "## Data Quality",
        f"Overall status: **{'Pass' if quality.get('passed') else 'Fail'}**",
        _markdown_table(quality_rows),
        "## Freshness",
        _markdown_table(
            [
                ("is_fresh", freshness.get("is_fresh")),
                ("latest_published", freshness.get("latest_published")),
                ("oldest_published", freshness.get("oldest_published")),
                ("stale_rows", freshness.get("stale_rows")),
                ("total_rows", freshness.get("total_rows")),
                ("freshness_threshold_days", freshness.get("freshness_threshold_days")),
            ]
        ),
        "## Ragas",
        f"```json\n{metrics.get('ragas', {})}\n```",
    ]
    write_text(Path(report_path), "\n\n".join(sections) + "\n")


def generate_corruption_report(
    report_path: Path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write an evidence-backed baseline/corrupted/repaired comparison report."""
    metric_rows = []
    for name in METRIC_NAMES:
        baseline = baseline_metrics.get(name)
        corrupted = corrupted_metrics.get(name)
        repaired = repaired_metrics.get(name)
        delta = corrupted - baseline if isinstance(corrupted, (int, float)) and isinstance(baseline, (int, float)) else None
        recovery = repaired - corrupted if isinstance(repaired, (int, float)) and isinstance(corrupted, (int, float)) else None
        metric_rows.append((name, baseline, corrupted, repaired, delta, recovery))

    lines = [
        "# Corruption and Repair Comparison",
        "## Evaluation Metrics",
        "| Metric | Baseline | Corrupted | Repaired | Corrupted - Baseline | Repaired - Corrupted |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {name} | {_display(baseline)} | {_display(corrupted)} | {_display(repaired)} | {_display(delta)} | {_display(recovery)} |"
        for name, baseline, corrupted, repaired, delta, recovery in metric_rows
    )
    lines.extend(
        [
            "",
            "## Data Quality and Freshness",
            "| Signal | Corrupted | Repaired |",
            "| --- | --- | --- |",
            f"| Quality passed | {_display(corrupted_quality.get('passed'))} | {_display(repaired_quality.get('passed'))} |",
            f"| Fresh | {_display(corrupted_freshness.get('is_fresh'))} | {_display(repaired_freshness.get('is_fresh'))} |",
            f"| Stale rows | {_display(corrupted_freshness.get('stale_rows'))} | {_display(repaired_freshness.get('stale_rows'))} |",
            "",
            "All comparisons use the same fixed evaluation set. Interpret recovery only from the values above and their linked artifacts.",
        ]
    )
    write_text(Path(report_path), "\n".join(lines) + "\n")
