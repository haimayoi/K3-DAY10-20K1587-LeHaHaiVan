from __future__ import annotations

import json
from pathlib import Path

from observability.reporting import generate_corruption_report


def test_corruption_report_includes_all_three_states(tmp_path: Path) -> None:
    report_path = tmp_path / "comparison.md"
    baseline_metrics = {
        "retrieval_hit_rate": 1.0,
        "mean_token_f1": 1.0,
        "judge_accuracy": 1.0,
        "mean_judge_score": 5.0,
    }
    corrupted_metrics = {
        "retrieval_hit_rate": 0.5,
        "mean_token_f1": 0.4,
        "judge_accuracy": 0.5,
        "mean_judge_score": 3.0,
    }
    quality_ok = {"passed": True, "row_count": 24, "checks": {"summary_not_null": {"passed": True}}}
    quality_bad = {"passed": False, "row_count": 24, "checks": {"summary_not_null": {"passed": False}}}
    fresh_ok = {"is_fresh": True, "stale_rows": 0, "missing_published": 0, "invalid_age_days": 0}
    fresh_bad = {"is_fresh": False, "stale_rows": 2, "missing_published": 0, "invalid_age_days": 0}
    generate_corruption_report(
        report_path,
        baseline_metrics,
        corrupted_metrics,
        baseline_metrics,
        quality_bad,
        quality_ok,
        fresh_bad,
        fresh_ok,
        baseline_quality=quality_ok,
        baseline_freshness=fresh_ok,
    )
    report = report_path.read_text(encoding="utf-8")
    assert "| Metric | Baseline | Corrupted | Repaired |" in report
    assert "| Failed quality checks | None | summary_not_null | None |" in report
    assert "| Stale rows | 0 | 2 | 0 | 2 | -2 |" in report
    assert "All comparisons use the same fixed evaluation set." in report


def test_committed_test_set_uses_real_clean_document_ids() -> None:
    root = Path(__file__).resolve().parents[1]
    test_set = json.loads((root / "data" / "eval" / "test_set.json").read_text(encoding="utf-8"))
    clean_ids = {
        line.split(",", 1)[0]
        for line in (root / "data" / "clean" / "papers_clean.csv").read_text(encoding="utf-8").splitlines()[1:]
    }
    assert test_set
    for sample in test_set:
        assert {"id", "question_type", "question", "ground_truth", "ground_truth_doc_ids"} <= sample.keys()
        assert set(sample["ground_truth_doc_ids"]).issubset(clean_ids)
