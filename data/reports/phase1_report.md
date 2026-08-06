# Phase 1 Baseline Report

## Source

| Item | Value |
| --- | --- |
| source | Crossref REST API |
| query | agentic retrieval augmented generation large language model |
| raw_count | 24 |
| clean_count | 24 |
| dropped_count | 0 |
| retention_rate | 1.0000 |
| missing_required_columns | [] |
| critical_empty_counts | {'paper_id': 0, 'title': 0, 'text_for_embedding': 0} |
| duplicate_paper_id_rows | 0 |

## Evaluation Metrics

| Item | Value |
| --- | --- |
| retrieval_hit_rate | 1.0000 |
| mean_token_f1 | 1.0000 |
| judge_accuracy | 1.0000 |
| mean_judge_score | 5 |
| samples | 12 |

## Data Quality

Overall status: **Pass**

| Item | Value |
| --- | --- |
| row_count | Pass |
| paper_id_not_null | Pass |
| paper_id_unique | Pass |
| title_not_null | Pass |
| summary_not_null | Pass |
| duplicate_rows | Pass |
| age_days_valid | Pass |

## Freshness

| Item | Value |
| --- | --- |
| is_fresh | Pass |
| latest_published | 2026-08-01 |
| oldest_published | 2026-02-12 |
| stale_rows | 0 |
| total_rows | 24 |
| freshness_threshold_days | 180 |

## Ragas

```json
{'skipped': 'Set RUN_RAGAS=1 to enable the slower Ragas pass.'}
```
