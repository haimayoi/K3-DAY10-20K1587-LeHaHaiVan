# Corruption and Repair Comparison
## RAG Metrics
| Metric | Baseline | Corrupted | Repaired |
| --- | ---: | ---: | ---: |
| retrieval_hit_rate | 1.0000 | 0.6667 | 1.0000 |
| mean_token_f1 | 1.0000 | 0.5141 | 1.0000 |
| judge_accuracy | 1.0000 | 0.5000 | 1.0000 |
| mean_judge_score | 5 | 3 | 5 |

## Quality Signals
| Signal | Baseline | Corrupted | Repaired |
| --- | ---: | ---: | ---: |
| quality_passed | Pass | Fail | Pass |
| row_count | 24 | 24 | 24 |
| paper_id_duplicate_rows | 0 | 4 | 0 |
| summary_missing | 0 | 4 | 0 |
| duplicate_rows | 0 | 2 | 0 |
| fresh | Pass | Fail | Pass |
| stale_rows | 0 | 2 | 0 |
| latest_published | 2026-08-01 | 2026-07-03 | 2026-08-01 |
| oldest_published | 2026-02-12 | 2000-01-01 | 2026-02-12 |

## Metric Delta
| Metric | Corrupted - Baseline | Repaired - Corrupted |
| --- | ---: | ---: |
| retrieval_hit_rate | -0.3333 | 0.3333 |
| mean_token_f1 | -0.4859 | 0.4859 |
| judge_accuracy | -0.5000 | 0.5000 |
| mean_judge_score | -2 | 2 |

All comparisons use the same fixed evaluation set. Interpret recovery only from the values above and their linked artifacts.
