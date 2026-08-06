# Corruption and Repair Comparison
## Evaluation Metrics
| Metric | Baseline | Corrupted | Repaired | Corrupted - Baseline | Repaired - Corrupted |
| --- | ---: | ---: | ---: | ---: | ---: |
| retrieval_hit_rate | 1.0000 | 0.6667 | 1.0000 | -0.3333 | 0.3333 |
| mean_token_f1 | 1.0000 | 0.5141 | 1.0000 | -0.4859 | 0.4859 |
| judge_accuracy | 1.0000 | 0.5000 | 1.0000 | -0.5000 | 0.5000 |
| mean_judge_score | 5 | 3 | 5 | -2 | 2 |

## Data Quality and Freshness
| Signal | Corrupted | Repaired |
| --- | --- | --- |
| Quality passed | Fail | Pass |
| Fresh | Fail | Pass |
| Stale rows | 2 | 0 |

All comparisons use the same fixed evaluation set. Interpret recovery only from the values above and their linked artifacts.
