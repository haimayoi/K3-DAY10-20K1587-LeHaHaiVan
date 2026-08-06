# Corruption and Repair Comparison
## Evaluation Metrics
| Metric | Baseline | Corrupted | Repaired | Corrupted - Baseline | Repaired - Corrupted |
| --- | ---: | ---: | ---: | ---: | ---: |
| retrieval_hit_rate | 1.0000 | 0.6667 | 1.0000 | -0.3333 | 0.3333 |
| mean_token_f1 | 1.0000 | 0.5141 | 1.0000 | -0.4859 | 0.4859 |
| judge_accuracy | 1.0000 | 0.5833 | 1.0000 | -0.4167 | 0.4167 |
| mean_judge_score | 5 | 3.5000 | 5 | -1.5000 | 1.5000 |

## Data Quality and Freshness
| Signal | Baseline | Corrupted | Repaired | Corrupted - Baseline | Repaired - Corrupted |
| --- | --- | --- | --- | --- | --- |
| Quality passed | Pass | Fail | Pass | N/A | N/A |
| Failed quality checks | None | paper_id_unique, summary_not_null, duplicate_rows | None | N/A | N/A |
| Row count | 24 | 24 | 24 | 0 | 0 |
| Fresh | Pass | Fail | Pass | N/A | N/A |
| Stale rows | 0 | 2 | 0 | 2 | -2 |
| Missing published dates | 0 | 0 | 0 | 0 | 0 |
| Invalid age days | 0 | 0 | 0 | 0 | 0 |

All comparisons use the same fixed evaluation set. Interpret recovery only from the values above and their linked artifacts.
