# Báo cáo cá nhân — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                                                             |
| ------------------ | --------------------------------------------------------------------- |
| Họ và tên       | Lê Hà Hải Vân                                                     |
| MSSV               | 2A202601587                                                           |
| Khóa/Lớp         | E402                                                                  |
| Tên nhóm         | B6                                                                    |
| Vai trò chính    | Data ingestion và cleaning owner                                     |
| Repository         | https://github.com/haimayoi/K3_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06                                                            |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable     | File/hàm phụ trách         | Input nhận vào            | Output bàn giao                        | Trạng thái |
| ---------------------- | ----------------------------- | --------------------------- | --------------------------------------- | ------------ |
| Raw ingestion          | `src/ingestion/crossref.py` | Crossref REST response      | Raw response và normalized raw records | Hoàn thành |
| Cleaning/data model    | `src/ingestion/cleaning.py` | `PaperRecord` list        | Clean CSV/JSON với schema downstream   | Hoàn thành |
| Repair-data validation | Raw snapshot, corruption log  | Raw/clean/corrupted records | Repair lineage xác minh khôi phục    | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                                    | Thành viên/module được hỗ trợ | Kết quả                                                                                                            |
| ----------------------------------------------- | ------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| Xác minh contract clean cho index và test set | Đức, Hùng                         | `paper_id`, `title`, `summary`, `published`, `age_days`, `text_for_embedding` có mặt và dùng được |
| Xác minh repair từ source tin cậy            | Hùng                                | `data/results/repair_lineage.json` có `passed: true`, không có blocker                                        |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện              | File/hàm/artifact liên quan                  | Kết quả bàn giao                             | Cách xác minh                                                         |
| ---------------------------------------- | ---------------------------------------------- | ----------------------------------------------- | ----------------------------------------------------------------------- |
| Lưu snapshot nguồn và parse stable ID | `crossref.py`, `data/raw/`                 | Crossref response và 24 normalized raw records | Kiểm tra`data/raw/crossref_response.json`, `crossref_records.json` |
| Chuẩn hóa và tạo clean contract      | `cleaning.py`, `data/clean/papers_clean.*` | 24 clean rows, đủ field downstream            | Baseline report: raw=24, clean=24, no missing critical field            |
| Kiểm chứng repair                      | `data/results/repair_lineage.json`           | Các record bị lỗi được restore và unique | Artifact ghi 24 raw/24 corrupted/24 repaired,`passed: true`           |

Output cụ thể: `data/clean/papers_clean.csv` là đầu vào chung cho index/evaluation. Nó giữ `paper_id` ổn định, `text_for_embedding` được tạo từ title + summary, và `age_days` cho freshness. Đây là contract giúp Đức tạo ground-truth IDs và Hùng build ba collection riêng.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Raw API data không phù hợp trực tiếp cho retrieval/evaluation: text có thể chứa whitespace không nhất quán, field ngày cần parse, author/category là list, và ID cần ổn định xuyên suốt pipeline. Nếu clean schema thay đổi hoặc mất ID, test set và index sẽ không còn đối chiếu được.

### Cách triển khai

Cleaning normalize `title`, `summary`, authors và categories; parse `published`; lọc title/summary quá ngắn hoặc date không hợp lệ; deduplicate theo `paper_id`; tính `age_days`; và tạo `text_for_embedding`. Lý do/count của record bị loại được giữ trong dataframe attributes. Với snapshot hiện tại, không có record nào bị lọc: 24 raw records trở thành 24 clean records.

### Input, output và contract

| Thành phần                   | Mô tả                                                                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| Input                          | `PaperRecord` từ `data/raw/crossref_records.json` gồm ID, title, summary, authors, categories, published và URL   |
| Output                         | Clean dataframe/CSV/JSON có`paper_id`, text fields, metadata, `age_days`, `summary_chars`, `text_for_embedding` |
| Module phụ thuộc             | `src/ingestion/crossref.py`, `src/core/utils.py`                                                                     |
| Module sử dụng output        | `testset.py`, `retrieval/index.py`, `phase1.py`, `corruption_flow.py`, `quality.py`                            |
| Điều kiện lỗi cần xử lý | Missing/too-short title/summary, unparseable date, duplicate`paper_id`                                                 |

### Cách xác minh

```bash
py -3.11 script/run_phase1.py
```

- **Kết quả mong đợi:** Raw và clean artifacts tồn tại; critical fields không rỗng; IDs unique.
- **Kết quả thực tế:** `raw_count=24`, `clean_count=24`, `dropped_count=0`, retention `1.0000`; baseline quality pass.
- **Artifact/log:** `data/clean/papers_clean.csv`, `data/reports/phase1_report.md`, `data/quality/baseline.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần một document key dùng chung cho raw, clean, Chroma, test set và repair.
- **Các phương án đã cân nhắc:** Dùng vị trí dòng/tựa đề; dùng DOI/ID nguồn làm `paper_id`.
- **Phương án đã chọn:** Dùng stable `paper_id` từ raw record, sau đó deduplicate theo ID này.
- **Lý do:** Row position thay đổi khi sort/filter/corrupt; title có thể bị trùng hoặc bị cắt ngắn. Stable ID giúp lineage và ground-truth kiểm chứng được.
- **Bằng chứng quyết định phù hợp:** Baseline có 0 duplicate ID; repair lineage chứng minh các record bị drop/duplicate quay lại một bản unique sau repair.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Sau corruption, số dòng cuối vẫn là 24 dù hai record mới nhất đã bị drop.
- **Lệnh hoặc bước tái hiện:** Chạy `py -3.11 script/run_corruption_flow.py`, sau đó đọc `data/results/corruption_log.json` và `data/quality/corrupted.json`.
- **Nguyên nhân gốc:** Hai duplicate rows được thêm vào đã bù đúng hai records bị drop; row count một mình không phát hiện mất document identity/content.
- **Cách xử lý:** Dùng thêm ID uniqueness, summary completeness, exact-duplicate checks và repair lineage; không kết luận pipeline tốt chỉ từ row count.
- **Cách xác minh sau khi sửa:** Corrupted quality fail với 4 duplicate-ID rows, 4 missing summaries, 2 exact duplicates; repaired quality pass.
- **Điều học được:** Data observability phải đo nhiều dimension; volume không thay thế được identity và completeness.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:** Crossref response được lưu rồi parse thành raw records; cleaning chuẩn hóa và tạo clean contract; index biến `text_for_embedding` thành MiniLM vectors trong Chroma. Đức tạo fixed test set từ clean `paper_id` và đo answers từ collection. Quality kiểm tra tính hợp lệ/completeness/uniqueness; freshness kiểm tra độ cũ của publication dựa trên `age_days`. Cùng test set phải được giữ nguyên để metric difference là do baseline/corrupted/repaired data state. Repair chỉ được xem là thành công khi raw-source lineage, quality/freshness và evaluation metrics cùng phục hồi.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét cá nhân                                                            |
| ---------------------- | -------: | --------: | -------: | ------------------------------------------------------------------------------- |
| `retrieval_hit_rate` |   1.0000 |    0.6667 |   1.0000 | Drop document và thay đổi text làm retrieval giảm; raw repair khôi phục. |
| `mean_token_f1`      |   1.0000 |    0.5141 |   1.0000 | Content corruption làm answer overlap giảm mạnh.                             |
| `judge_accuracy`     |   1.0000 |    0.5833 |   1.0000 | Correctness giảm theo chất lượng data/index.                                |
| `mean_judge_score`   |   5.0000 |    3.5000 |   5.0000 | Repaired quay lại baseline.                                                    |
| Quality checks         |     Pass |      Fail |     Pass | Corrupted fail uniqueness, summary completeness và duplicate rows.             |
| Freshness status       |    Fresh |     Stale |    Fresh | Stale rows: 0 → 2 → 0.                                                        |

### Kết luận từ số liệu

1. Drop/duplicate/blank summary → unique/completeness checks fail và document availability giảm → retrieval/answer metrics giảm.
2. Chạy lại cleaning từ raw snapshot → ID, title, summary và date được restore → quality/freshness và tất cả metrics về baseline.

Kịch bản rõ nhất là sự kết hợp drop record và duplicate row: row count không đổi nhưng retrieval hit rate giảm 0.3333. Điều này cho thấy row count là signal cần thiết nhưng không đủ.

Kết quả khác kỳ vọng ban đầu là final corrupted row count vẫn bằng baseline. Log corruption và quality report đã được dùng để kiểm tra nguyên nhân thay vì suy diễn chỉ từ count.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Raw snapshot và stable document ID là nền tảng cho recovery có thể kiểm chứng.
2. Clean schema là contract của các module sau, không chỉ là output trung gian.
3. Row count không đổi không chứng minh dữ liệu đúng; phải kết hợp quality và lineage.

### Nếu có thêm thời gian

Tôi sẽ bổ sung artifact ghi đầy đủ record IDs và lý do filter/dedupe ở mọi run, kèm checksum raw snapshot để tăng auditability.

## 10. Cam kết của thành viên

- [X] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [X] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [X] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [X] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [X] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [X] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Lê Hà Hải Vân
**Ngày xác nhận:** 2026-08-06
