# Báo cáo nhóm — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                                                             |
| ------------------ | --------------------------------------------------------------------- |
| Khóa/Lớp         | E402                                                                  |
| Tên nhóm         | B6                                                                    |
| Repository         | https://github.com/haimayoi/K3_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06                                                            |

| STT | Thành viên      | MSSV        | Vai trò chính              | Module/deliverable phụ trách                                                                      |
| --: | ----------------- | ----------- | ---------------------------- | --------------------------------------------------------------------------------------------------- |
|   1 | Lê Hà Hải Vân | 2A202601587 | Ingestion và cleaning       | `src/ingestion/crossref.py`, `src/ingestion/cleaning.py`, raw/clean artifacts                   |
|   2 | Tạ Minh Đức    | 2A202601497 | Evaluation và observability | `src/evaluation/testset.py`, `src/observability/quality.py`, `src/observability/reporting.py` |
|   3 | Hà Duyên Hùng  | 2A202601465 | Corruption và integration   | `src/ingestion/corruption.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`  |

## 2. Tóm tắt kết quả

Nhóm đã xây dựng pipeline Crossref-to-RAG cho truy vấn `agentic retrieval augmented generation large language model`. Snapshot nguồn được lưu gồm 24 raw records; cleaning giữ lại toàn bộ 24 records. Baseline tạo ra clean CSV/JSON, embedding manifest MiniLM/Chroma, test set cố định 12 câu, answers/metrics, quality/freshness JSON và baseline report.

Corruption có kiểm soát gồm sáu kịch bản: xóa hai record mới nhất, làm rỗng hai summary, thêm nhiễu vào hai summary, cắt ngắn hai title, làm cũ hai ngày xuất bản và thêm hai dòng trùng. Dù số dòng cuối cùng vẫn là 24, quality bị fail vì có 4 dòng trùng `paper_id`, 4 dòng summary rỗng và 2 dòng trùng hoàn toàn. Freshness cũng fail vì có 2 stale rows. `retrieval_hit_rate` giảm từ 1.0000 xuống 0.6667, `mean_token_f1` giảm từ 1.0000 xuống 0.5141, `judge_accuracy` giảm từ 1.0000 xuống 0.5833 và `mean_judge_score` giảm từ 5.0000 xuống 3.5000.

Repair chạy lại từ raw snapshot bất biến, không sửa tay output corrupted. Toàn bộ metric, quality và freshness của repaired quay lại đúng baseline. Ragas chưa chạy; artifact ghi rõ trạng thái `skipped` thay vì coi đó là điểm thành công.

## 3. Kiến trúc và luồng dữ liệu

```text
Crossref REST API
  → raw response + raw records đã chuẩn hóa
  → cleaning và data modeling
  → MiniLM embeddings + Chroma collections
  → test set cố định + baseline evaluation
  → quality và freshness reports
  → corruption + re-index + re-evaluate
  → repair từ raw snapshot + re-index + re-evaluate
  → comparison report và repair lineage
```

| Khối             | Input                          | Xử lý chính                                                      | Output/artifact                                                         | Owner |
| ----------------- | ------------------------------ | ------------------------------------------------------------------- | ----------------------------------------------------------------------- | ----- |
| Ingestion         | Crossref REST response         | Fetch, retry/backoff, parse stable ID                               | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Vân  |
| Cleaning          | Raw records                    | Normalize text, parse date, dedupe, tạo embedding text/age         | `data/clean/papers_clean.csv`, `data/clean/papers_clean.json`       | Vân  |
| Embedding/index   | Clean dataframe                | `sentence-transformers/all-MiniLM-L6-v2`, collections tách biệt | `data/embeddings/*.json`                                              | Hùng |
| Evaluation        | Test set cố định và index  | Exact-title lookup, semantic retrieval, chấm điểm                | `data/results/*_answers.json`, `*_metrics.json`                     | Đức |
| Observability     | Ba dataframe trạng thái      | Bảy quality checks và freshness report                            | `data/quality/*.json`, `data/reports/*.md`                          | Đức |
| Corruption/repair | Clean dataset và raw snapshot | Sáu corruption xác định; rebuild từ raw                        | Corruption log, lineage, repaired artifacts                             | Hùng |
| Orchestration     | Mọi artifact đầu vào       | Điều phối CP1/CP5/CP6 và isolation checks                       | `phase1.py`, `corruption_flow.py`, CP6 checklist                    | Hùng |

## 4. Cách tái hiện

| Cấu hình                  | Giá trị thực tế                                                       |
| --------------------------- | ------------------------------------------------------------------------- |
| Source                      | Crossref REST API                                                         |
| Query                       | `agentic retrieval augmented generation large language model`           |
| Số source records tối đa | 24                                                                        |
| Embedding model             | `sentence-transformers/all-MiniLM-L6-v2`                                |
| Vector store                | ChromaDB; baseline/corrupted/repaired collections tách biệt             |
| Retrieval top-k             | 4                                                                         |
| Freshness threshold         | 180 ngày                                                                 |
| Chọn record corruption     | Deterministic sau khi sắp xếp theo`paper_id`; không cần random seed |
| LLM provider/model          | Có thể cấu hình; mặc định Gemini /`gemini-2.5-flash`             |

Cài đặt bằng `uv sync` hoặc `py -3.11 -m pip install -e .`. Chạy baseline bằng `py -3.11 script/run_phase1.py` và chạy corruption/repair bằng `py -3.11 script/run_corruption_flow.py`. Ragas chỉ chạy khi bật `RUN_RAGAS=1`.

## 5. Ingestion, cleaning và data contract

| Trường                                 | Kiểu    | Bắt buộc | Ý nghĩa                                    | Xử lý                                                 |
| ---------------------------------------- | -------- | ---------- | -------------------------------------------- | ------------------------------------------------------- |
| `paper_id`                             | string   | Có        | Stable document identity và ground-truth ID | Thiếu/trùng sẽ fail quality; cleaning dedupe theo ID |
| `title`                                | string   | Có        | Text hiển thị và retrieval                | Normalize; title quá ngắn bị loại                   |
| `summary`                              | string   | Có        | Nội dung bằng chứng chính                | Normalize; summary quá ngắn bị loại                 |
| `published`                            | ISO date | Có        | Freshness và câu hỏi ngày tháng         | Date không parse được bị loại                     |
| `authors_joined`/`categories_joined` | string   | Không     | Metadata để trả lời                      | Giá trị được normalize/join                        |
| `age_days`                             | integer  | Có        | Input freshness có thể tái lập           | Tính trong cleaning từ run date                       |
| `text_for_embedding`                   | string   | Có        | Nội dung đưa vào index                   | `title + summary` sau normalize                       |

Raw count và clean count đều bằng 24; `dropped_count` bằng 0, retention bằng 1.0000. Baseline không có missing required columns, empty critical fields hoặc duplicate `paper_id`.

## 6. Thiết lập evaluation

| Thành phần      | Cấu hình thực tế                                     |
| ----------------- | -------------------------------------------------------- |
| Số câu hỏi     | 12                                                       |
| `question_type` | `summary`, `date`, `authors`, `categories`       |
| Ground-truth IDs  | Lấy trực tiếp từ`paper_id` của clean dataset      |
| Test-set path     | `data/eval/test_set.json`                              |
| Index             | ChromaDB với MiniLM embeddings                          |
| Retrieval top-k   | 4                                                        |
| Quy tắc so sánh | Cùng một test set cho baseline, corrupted và repaired |

Giữ nguyên test set giúp thay đổi metric phản ánh data/index state thay vì thay đổi câu hỏi hoặc document IDs.

## 7. Kết quả baseline

| Artifact                 | Đường dẫn                                                     | Trạng thái    |
| ------------------------ | ----------------------------------------------------------------- | --------------- |
| Raw snapshot             | `data/raw/`                                                     | Có             |
| Clean dataset            | `data/clean/papers_clean.csv`, `data/clean/papers_clean.json` | Có; 24 rows    |
| Embedding manifest       | `data/embeddings/papers_embeddings.json`                        | Có             |
| Evaluation set           | `data/eval/test_set.json`                                       | Có; 12 samples |
| Baseline answers/metrics | `data/results/baseline_answers.json`, `baseline_metrics.json` | Có             |
| Quality/freshness        | `data/quality/baseline.json`, `freshness_report.json`         | Có và pass    |
| Baseline report          | `data/reports/phase1_report.md`                                 | Có             |

| Metric                 | Baseline | Diễn giải                                                        |
| ---------------------- | -------: | ------------------------------------------------------------------ |
| `retrieval_hit_rate` |   1.0000 | Mọi test item đều retrieve đúng ground-truth document ID.     |
| `mean_token_f1`      |   1.0000 | Extracted answer khớp reference tokens trên test set cố định. |
| `judge_accuracy`     |   1.0000 | Mọi answer được đánh giá materially correct.                |
| `mean_judge_score`   |   5.0000 | Điểm judge trung bình tối đa.                                 |
| Ragas                  |  Skipped | Chưa bật`RUN_RAGAS`.                                           |

## 8. Data quality và freshness

Bảy baseline checks đều pass: row count khác rỗng, ID không null, ID unique, title không null, summary không null, không duplicate row và `age_days` hợp lệ. Baseline freshness là fresh: latest publication `2026-08-01`, oldest `2026-02-12`, 0 stale rows, 0 missing published dates và ngưỡng 180 ngày.

## 9. Corruption và repair

| Kịch bản              | Record tác động | Hiệu ứng quan sát                                                | Cách repair                             |
| ----------------------- | -----------------: | ------------------------------------------------------------------- | ---------------------------------------- |
| Drop latest records     |                  2 | Ground-truth document không còn trong corrupted index             | Rebuild từ raw khôi phục hai ID       |
| Blank summaries         |                  2 | Summary completeness fail; bản sao trùng làm thành 4 blank rows | Rebuild khôi phục summary gốc         |
| Add summary noise       |                  2 | Retrieved content bị suy giảm                                     | Rebuild loại injected prefix            |
| Truncate titles         |                  2 | Exact-title retrieval bị yếu đi                                  | Rebuild khôi phục full title           |
| Make publications stale |                  2 | Freshness fail với 2 stale rows                                    | Rebuild khôi phục date và`age_days` |
| Add duplicate rows      |       2 dòng copy | 4 duplicate-ID rows và 2 exact duplicate rows                      | Cleaning từ raw khôi phục unique IDs  |

Log đầy đủ nằm ở `data/results/corruption_log.json`. `data/results/repair_lineage.json` xác minh các record bị tác động đều tồn tại và unique sau repair; artifact có `passed: true` và không có blocker.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal          | Baseline | Corrupted | Repaired | Corrupted − baseline | Repaired − corrupted | Nhận xét                                                       |
| ---------------------- | -------: | --------: | -------: | --------------------: | --------------------: | ---------------------------------------------------------------- |
| `retrieval_hit_rate` |   1.0000 |    0.6667 |   1.0000 |               -0.3333 |                0.3333 | Retrieval khôi phục hoàn toàn.                               |
| `mean_token_f1`      |   1.0000 |    0.5141 |   1.0000 |               -0.4859 |                0.4859 | Token overlap khôi phục hoàn toàn.                           |
| `judge_accuracy`     |   1.0000 |    0.5833 |   1.0000 |               -0.4167 |                0.4167 | Tính đúng đắn khôi phục hoàn toàn.                      |
| `mean_judge_score`   |   5.0000 |    3.5000 |   5.0000 |               -1.5000 |                1.5000 | Chất lượng answer khôi phục hoàn toàn.                    |
| Quality                |     Pass |      Fail |     Pass |                   N/A |                   N/A | Corrupted fail: ID unique, summary completeness, duplicate rows. |
| Freshness              |    Fresh |     Stale |    Fresh |                   N/A |                   N/A | Stale rows: 0 → 2 → 0.                                         |

Kết luận có bằng chứng:

1. Drop document, blank summary, truncate title, thêm noise, stale date và duplicate làm quality/freshness fail, đồng thời làm giảm các metric trên test set không đổi.
2. Chạy lại cleaning từ raw snapshot khôi phục document identity và content; quality/freshness pass và mọi evaluation metric quay về baseline.

## 11. Vấn đề tích hợp và cách xử lý

- **Triệu chứng:** Chroma index binaries sinh ra thay đổi repository lớn và phụ thuộc môi trường.
- **Nguyên nhân:** Persistent vector store ghi SQLite và binary index dưới `data/chroma/`.
- **Cách xử lý:** Repository không còn theo dõi regenerated Chroma binaries và ignore `data/chroma/`; pipeline/manifest có thể tạo lại collection khi cần.
- **Xác minh:** CP6 checklist xác nhận mỗi collection có 24 documents; không có tracked `.env`, potential secret file hoặc hard-coded absolute path trong tracked files đã scan.

## 12. Giới hạn và hướng cải thiện

| Giới hạn                                               | Ảnh hưởng                                           | Cải thiện có thể kiểm chứng                                                              |
| -------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| Test set chỉ có 12 câu trên 3 documents              | Đây là smoke test hẹp, chưa phải benchmark rộng | Lấy thêm paper sạch nhưng giữ ID deterministic và cùng test set giữa các trạng thái |
| Ragas bị skip                                           | Không có Ragas score                                 | Chạy với`RUN_RAGAS=1` và lưu configuration/output                                        |
| Answer layer thiên về extractive, hỗ trợ exact title | Metric có thể lạc quan với câu hỏi exact-title   | Bổ sung câu paraphrase, multi-hop và blind retrieval evaluation                             |
| Crossref là nguồn live                                 | Refresh có thể thay đổi corpus                     | Version raw snapshot, lưu timestamp/checksum rõ ràng                                        |

## 13. Checklist trước khi nộp

- [X] Vai trò, module và artifacts của nhóm đã được mô tả.
- [X] Baseline/corrupted/repaired dùng cùng test set.
- [X] Metrics và kết luận khớp `data/results/` và `data/quality/`.
- [X] Reports, lineage và checklist artifacts đều tồn tại.
- [X] CP6 check không phát hiện tracked `.env`, likely secret hoặc hard-coded absolute path.
