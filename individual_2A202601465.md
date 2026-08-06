# Individual Report - 2A202601465

## 1. Vai trò cá nhân

Trong nhóm 3, tôi đảm nhận vai trò **TV3 - Corruption & Integration owner**. Theo phân công trong `TeamGuide_Nhom3.md`, TV3 phụ trách các file/module chính:

- `src/ingestion/corruption.py`
- `src/pipelines/phase1.py`
- `src/pipelines/corruption_flow.py`

Ngoài các file sở hữu chính, tôi cũng có một số thay đổi tích hợp liên quan đến index/report để đảm bảo pipeline chạy end-to-end và artifact có thể tái lập trên máy khác.

## 2. Module sở hữu và phạm vi công việc

### 2.1. Baseline orchestration - `phase1.py`

Module `src/pipelines/phase1.py` điều phối baseline pipeline theo đúng thứ tự:

```text
raw -> clean -> index -> test set -> evaluate -> quality -> freshness -> report
```

Minh chứng code:

- `src/pipelines/phase1.py:54` - load raw snapshot hoặc fetch source.
- `src/pipelines/phase1.py:67` - kiểm tra contract raw count -> clean count.
- `src/pipelines/phase1.py:124` - hàm `main()` chạy toàn bộ phase 1.
- `src/pipelines/phase1.py:144` - build Chroma index baseline.
- `src/pipelines/phase1.py:153` - tạo/load fixed test set.
- `src/pipelines/phase1.py:163` - evaluate baseline.
- `src/pipelines/phase1.py:171` - chạy quality checks.
- `src/pipelines/phase1.py:173` - chạy freshness report.
- `src/pipelines/phase1.py:189` - generate baseline report.

Ý nghĩa:

- Không cho index/test set/evaluation chạy nếu clean schema chưa ổn định.
- Nếu raw/clean count bất thường hoặc thiếu cột bắt buộc, pipeline dừng bằng blocker có evidence.
- Baseline được chốt thành mốc so sánh cho corrupted và repaired.

Artifact liên quan:

- `data/clean/papers_clean.csv`
- `data/clean/papers_clean.json`
- `data/embeddings/papers_embeddings.json`
- `data/eval/test_set.json`
- `data/results/baseline_metrics.json`
- `data/results/baseline_answers.json`
- `data/quality/baseline.json`
- `data/quality/freshness_report.json`
- `data/reports/phase1_report.md`

### 2.2. Corruption scenarios - `corruption.py`

Module `src/ingestion/corruption.py` tạo corrupted clean dataset có chủ đích và có log bằng chứng. Hàm chính là `corrupt_clean_dataframe(...)`.

Minh chứng code:

- `src/ingestion/corruption.py:50` - hàm `corrupt_clean_dataframe`.
- `src/ingestion/corruption.py:71` - `drop_latest_records`.
- `src/ingestion/corruption.py:94` - `blank_summary`.
- `src/ingestion/corruption.py:118` - `add_summary_noise`.
- `src/ingestion/corruption.py:139` - `truncate_title`.
- `src/ingestion/corruption.py:165` - `make_publication_stale`.
- `src/ingestion/corruption.py:181` - `add_duplicate_rows`.

Sau mỗi corruption, module ghi lại:

- `record_ids`
- `corruption_type`
- `parameters`
- `before_count`
- `after_count`
- `changes`

6 loại corruption đã implement:

| Loại corruption | Mô tả |
| --- | --- |
| `drop_latest_records` | Xóa một số record mới nhất theo `published`. |
| `blank_summary` | Làm rỗng trường `summary`. |
| `add_summary_noise` | Thêm noise/boilerplate vào `summary`. |
| `truncate_title` | Cắt ngắn `title`. |
| `make_publication_stale` | Đổi `published` thành ngày cũ và set `age_days` lớn. |
| `add_duplicate_rows` | Thêm duplicate rows để tạo lỗi trùng lặp. |

Minh chứng artifact:

- `data/results/corruption_log.json:6` - danh sách 6 corruption types.
- `data/results/corruption_log.json:15` - event `drop_latest_records`.
- `data/results/corruption_log.json:39` - event `blank_summary`.
- `data/results/corruption_log.json:64` - event `add_summary_noise`.
- `data/results/corruption_log.json:89` - event `truncate_title`.
- `data/results/corruption_log.json:114` - event `make_publication_stale`.
- `data/results/corruption_log.json:143` - event `add_duplicate_rows`.

Minh chứng test:

- `tests/test_corruption.py:51` - test xác nhận đủ 6 corruption types.
- `tests/test_corruption.py` kiểm tra input dataframe không bị mutate, log có before/after count, và output có đúng lỗi dữ liệu mong muốn.

### 2.3. Corruption, repair, comparison flow - `corruption_flow.py`

Module `src/pipelines/corruption_flow.py` là pipeline tích hợp CP5 và CP6.

Luồng chạy:

```text
baseline artifact check
-> corrupt clean data
-> build collection papers-corrupted
-> evaluate corrupted
-> quality/freshness corrupted
-> repair từ raw snapshot
-> build collection papers-repaired
-> evaluate repaired
-> quality/freshness repaired
-> generate comparison report
-> final checklist
```

Minh chứng code:

- `src/pipelines/corruption_flow.py:48` - require corrupted artifacts trước khi comparison.
- `src/pipelines/corruption_flow.py:69` - đảm bảo baseline/corrupted/repaired dùng path và collection riêng.
- `src/pipelines/corruption_flow.py:131` - normalize managed embedding manifest, tránh hard-code absolute path.
- `src/pipelines/corruption_flow.py:245` - build repair lineage evidence cho record bị corrupt/drop.
- `src/pipelines/corruption_flow.py:369` - check tracked secret và hard-coded absolute path.
- `src/pipelines/corruption_flow.py:416` - hàm `main()` điều phối toàn bộ flow.
- `src/pipelines/corruption_flow.py:490` - repair bằng cách re-run cleaning từ raw snapshot.
- `src/pipelines/corruption_flow.py:560` - generate comparison report từ artifact metrics/quality/freshness thật.

Ý nghĩa của repair:

- Repair không copy/sửa tay từ baseline.
- Repair load lại `data/raw/crossref_records.json`, chạy lại `build_clean_dataframe(...)`, rồi build collection riêng `papers-repaired`.
- Việc repaired quay về bằng baseline là kết quả hợp lý vì corruption xảy ra ở clean layer và raw snapshot còn nguyên.
- Kết luận đúng là: pipeline có thể phục hồi về trạng thái baseline trong điều kiện raw source còn tin cậy, không phải model tự sửa lỗi 100%.

### 2.4. Index contract fix - `index.py`

Trong quá trình tích hợp, tôi sửa contract embedding manifest để artifact không bị dính đường dẫn máy cá nhân.

Minh chứng code:

- `src/retrieval/index.py:84` - `_manifest_persist_path(...)` ghi path managed collection ở dạng relative, ví dụ `data/chroma`.
- `src/retrieval/index.py:91` - `_resolve_persist_path(...)` resolve managed collections theo current project settings.
- `src/retrieval/index.py:106` - `build(...)` sinh Chroma collection và embedding manifest.
- `src/retrieval/index.py:154` - `load(...)` load lại index từ manifest.

Minh chứng artifact:

- `data/embeddings/papers_embeddings.json` hiện dùng `"persist_path": "data/chroma"` thay vì absolute path.
- `data/embeddings/papers_embeddings_corrupted.json` dùng collection `papers-corrupted`.
- `data/embeddings/papers_embeddings_repaired.json` dùng collection `papers-repaired`.

## 3. Kết quả artifact thực tế

### 3.1. Baseline metrics

File: `data/results/baseline_metrics.json`

| Metric | Giá trị |
| --- | ---: |
| samples | 12 |
| retrieval_hit_rate | 1.0000 |
| mean_token_f1 | 1.0000 |
| judge_accuracy | 1.0000 |
| mean_judge_score | 5 |

### 3.2. Corrupted metrics

File: `data/results/corrupted_metrics.json`

| Metric | Giá trị |
| --- | ---: |
| samples | 12 |
| retrieval_hit_rate | 0.6667 |
| mean_token_f1 | 0.5141 |
| judge_accuracy | 0.5833 |
| mean_judge_score | 3.5000 |

### 3.3. Repaired metrics

File: `data/results/repaired_metrics.json`

| Metric | Giá trị |
| --- | ---: |
| samples | 12 |
| retrieval_hit_rate | 1.0000 |
| mean_token_f1 | 1.0000 |
| judge_accuracy | 1.0000 |
| mean_judge_score | 5 |

### 3.4. Quality và freshness signals

File:

- `data/quality/baseline.json`
- `data/quality/corrupted.json`
- `data/quality/repaired.json`
- `data/quality/freshness_report.json`
- `data/quality/corrupted-freshness.json`
- `data/quality/repaired-freshness.json`

| Signal | Baseline | Corrupted | Repaired |
| --- | --- | --- | --- |
| Quality passed | Pass | Fail | Pass |
| Row count | 24 | 24 | 24 |
| Duplicate paper_id rows | 0 | 4 | 0 |
| Missing summary | 0 | 4 | 0 |
| Duplicate rows | 0 | 2 | 0 |
| Fresh | Pass | Fail | Pass |
| Stale rows | 0 | 2 | 0 |

### 3.5. Comparison report

File: `data/reports/corruption_report.md`

Report có bảng so sánh baseline/corrupted/repaired và delta cho các metric chính:

- `retrieval_hit_rate`
- `mean_token_f1`
- `judge_accuracy`
- `mean_judge_score`

Minh chứng:

- `data/reports/corruption_report.md` có RAG metrics cho 3 trạng thái.
- `data/reports/corruption_report.md` có quality/freshness signals cho 3 trạng thái.
- `data/reports/corruption_report.md` có delta corrupted-baseline và repaired-corrupted.

## 4. Minh chứng repair lineage

File: `data/results/repair_lineage.json`

Kết quả hiện tại:

- `raw_count`: 24
- `corrupted_count`: 24
- `repaired_count`: 24
- `passed`: true
- `blockers`: []

Một số minh chứng lineage:

- Record bị `drop_latest_records` có `corrupted_count = 0`, `repaired_count = 1`, và `dropped_record_restored = true`.
- Record bị `blank_summary` có `blank_summary_restored = true`.
- Record bị `add_summary_noise` có `summary_noise_removed = true`.
- Record bị `truncate_title` có `title_restored = true`.
- Record bị `make_publication_stale` có `published_restored = true`.
- Record bị `add_duplicate_rows` có `duplicate_removed = true`.

Điều này chứng minh repaired dataset được tạo lại từ raw source và có thể phục hồi các lỗi corruption có chủ đích.

## 5. Checklist CP6

File: `data/results/cp6_checklist.json`

Kết quả:

- `repaired_metrics_exists`: true
- `comparison_report_exists`: true
- `baseline_collection_rows`: 24
- `corrupted_collection_rows`: 24
- `repaired_collection_rows`: 24
- `tracked_env_files`: []
- `potential_secret_files`: []
- `hardcoded_absolute_path_files`: []

PowerShell checkpoint:

```powershell
Test-Path data\results\repaired_metrics.json
Test-Path data\reports\corruption_report.md
```

Cả hai file đều tồn tại trong repo sau khi chạy CP6.

## 6. Lệnh kiểm chứng đã dùng

```powershell
.\.venv\Scripts\python.exe -m compileall src script tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:ANONYMIZED_TELEMETRY='False'
$env:RUN_RAGAS='0'
$env:OPENAI_API_KEY='checkpoint-local-fallback'
$env:OPENAI_BASE_URL='http://127.0.0.1:9/v1'
.\.venv\Scripts\python.exe script\run_corruption_flow.py
git diff --check
```

Ghi chú: Ragas được skip bằng `RUN_RAGAS=0` để flow nhanh và ổn định trong checkpoint. LLM judge có fallback heuristic khi endpoint không khả dụng, vì vậy kết quả metric được lấy từ artifact thật trên disk và cần ghi rõ khi demo.

## 7. Giới hạn và cách giải thích khi demo

Kết quả repaired bằng baseline không có nghĩa là hệ thống "tự động sửa mọi lỗi dữ liệu". Ý nghĩa đúng của CP6 là:

- Corruption được tạo có chủ đích ở clean layer.
- Raw snapshot vẫn còn nguyên vẹn và được xem là source đáng tin cậy.
- Repair chạy lại cleaning deterministic từ raw snapshot.
- Cùng test set, evaluator, top-k và collection riêng được dùng cho baseline/corrupted/repaired.
- Vì vậy repaired quay lại bằng baseline là kết quả hợp lý và có thể giải thích bằng lineage artifact.

Nếu chỉ copy baseline thành repaired thì không chứng minh được pipeline phục hồi. Flow hiện tại có ý nghĩa vì nó chứng minh được khả năng tái lập dữ liệu sạch, rebuild index, evaluate lại và so sánh bằng artifact thật.

## 8. Kết luận cá nhân

Phần việc TV3 đã hoàn thành các mục tiêu chính:

- Điều phối baseline pipeline trong `phase1.py`.
- Implement corruption có log trong `corruption.py`.
- Điều phối corrupted và repaired flow trong `corruption_flow.py`.
- Đảm bảo path/collection riêng cho `papers-baseline`, `papers-corrupted`, `papers-repaired`.
- Sinh comparison report từ artifact thật.
- Kiểm tra secret/hard-code path và artifact checklist trước khi kết luận phục hồi.

Kết quả cuối cùng cho thấy corruption làm giảm RAG metrics và làm fail quality/freshness; repair từ raw snapshot đưa metrics và quality/freshness về trạng thái baseline.
