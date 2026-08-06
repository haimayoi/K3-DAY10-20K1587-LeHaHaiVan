# Báo cáo cá nhân — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                                                             |
| ------------------ | --------------------------------------------------------------------- |
| Họ và tên       | Hà Duyên Hùng                                                      |
| MSSV               | 2A202601465                                                           |
| Khóa/Lớp         | E402                                                                  |
| Tên nhóm         | B6                                                                    |
| Vai trò chính    | Corruption và integration owner                                      |
| Repository         | https://github.com/haimayoi/K3_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06                                                            |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable     | File/hàm phụ trách                | Input nhận vào                    | Output bàn giao                                             | Trạng thái |
| ---------------------- | ------------------------------------ | ----------------------------------- | ------------------------------------------------------------ | ------------ |
| Controlled corruption  | `src/ingestion/corruption.py`      | Baseline clean dataframe            | Corrupted dataframe và event log                            | Hoàn thành |
| Baseline orchestration | `src/pipelines/phase1.py`          | Raw snapshot                        | Clean/index/evaluation/quality/report baseline artifacts     | Hoàn thành |
| CP5/CP6 integration    | `src/pipelines/corruption_flow.py` | Baseline artifacts và raw snapshot | Corrupted/repaired artifacts, lineage, comparison, checklist | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                      | Thành viên/module được hỗ trợ | Kết quả                                                                   |
| --------------------------------- | ------------------------------------ | --------------------------------------------------------------------------- |
| Handoff clean → index/evaluation | Vân, Đức                          | Clean contract được gate trước index; test set được giữ cố định |
| Kiểm tra evidence/report cuối   | Đức                                | CP6 checklist, repair lineage và comparison report đồng nhất            |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện      | File/hàm/artifact liên quan                    | Kết quả bàn giao                                              | Cách xác minh                                                         |
| -------------------------------- | ------------------------------------------------ | ---------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Điều phối baseline end-to-end | `phase1.py`                                    | Raw → clean → index → evaluate → quality/freshness → report | `data/reports/phase1_report.md` và baseline artifacts tồn tại      |
| Tạo corruption có log          | `corruption.py`, `corruption_log.json`       | 6 scenario, record IDs, parameters, before/after counts          | Đọc`data/results/corruption_log.json`                               |
| Repair và comparison            | `corruption_flow.py`, lineage/checklist/report | Repaired index, metrics, quality/freshness và recovery evidence | `repair_lineage.json` pass; CP6 checklist có đủ 24 rows/collection |

Output cụ thể là `data/results/repair_lineage.json`: nó nối record bị corruption với raw source và repaired state, xác nhận dropped record được restore, duplicate bị loại, blank/noisy summary và truncated title được phục hồi, stale publication được trả về giá trị gốc.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline cần chứng minh data corruption có tác động thật đến RAG, trong khi baseline phải không bị ghi đè. Sau đó repair phải tái lập được từ trusted source thay vì chỉnh tay metrics/answers.

### Cách triển khai

Flow kiểm tra baseline artifacts và separation của path/collection trước khi chạy. Corruption deterministic thực hiện sáu lỗi trên clean dataframe và log mọi event. Corrupted collection được build riêng; fixed test set được đánh giá lại; quality/freshness được ghi path riêng. Repair reload raw snapshot, rebuild clean data/index, re-evaluate bằng test set cũ, tạo repaired quality/freshness và comparison report. Hash/count guards kiểm tra baseline không đổi; collection count guards kiểm tra từng collection có đúng số documents.

### Input, output và contract

| Thành phần                   | Mô tả                                                                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| Input                          | Baseline clean/embedding/test-set/metrics artifacts, raw records snapshot, settings paths                                             |
| Output                         | Corrupted/repaired clean JSON/CSV, embeddings, answers, metrics, quality/freshness, corruption log, repair lineage, comparison report |
| Module phụ thuộc             | `cleaning.py`, `corruption.py`, `index.py`, `metrics.py`, `quality.py`, `reporting.py`                                    |
| Module sử dụng output        | Báo cáo nhóm/cá nhân, demo và CP6 checklist                                                                                     |
| Điều kiện lỗi cần xử lý | Baseline artifact thiếu, output path trùng baseline, collection name trùng, count/hash thay đổi ngoài ý muốn                  |

### Cách xác minh

```bash
py -3.11 script/run_phase1.py
py -3.11 script/run_corruption_flow.py
py -3.11 -m pytest -q
```

- **Kết quả mong đợi:** Baseline không bị overwrite; corrupted có impact đo được; repair từ raw phục hồi artifacts và metrics.
- **Kết quả thực tế:** Mỗi baseline/corrupted/repaired collection có 24 rows; repair lineage `passed: true`; repaired metrics bằng baseline.
- **Artifact/log:** `data/results/corruption_log.json`, `repair_lineage.json`, `cp6_checklist.json`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần so sánh ba trạng thái mà không làm biến đổi baseline hoặc dùng lại index sai collection.
- **Các phương án đã cân nhắc:** Dùng chung một Chroma collection/path; dùng collection/path riêng cho baseline, corrupted và repaired.
- **Phương án đã chọn:** Tách collection names và artifact paths cho từng trạng thái, có collision/count/hash checks.
- **Lý do:** Dùng chung collection có thể xóa/ghi đè baseline, khiến comparison không còn đáng tin cậy.
- **Bằng chứng quyết định phù hợp:** CP6 checklist xác nhận baseline/corrupted/repaired collection đều có 24 rows; lineage và comparison report tồn tại; baseline outputs được hash-guard.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Chroma persistent index tạo SQLite/binary files dưới `data/chroma/`, làm Git có nhiều regenerated binaries và thay đổi khó review.
- **Lệnh hoặc bước tái hiện:** Build một collection rồi chạy `git status`.
- **Nguyên nhân gốc:** Vector store persist index là runtime artifact phụ thuộc môi trường, không phải source artifact cần version như code/metrics/manifest.
- **Cách xử lý:** Stop tracking regenerated Chroma binaries và thêm ignore rule cho `data/chroma/`; giữ pipeline/manifest để có thể build lại collection.
- **Cách xác minh sau khi sửa:** CP6 checklist vẫn xác minh 24 documents cho mỗi collection; secret/path scan pass; code/artifacts cần thiết còn tồn tại.
- **Điều học được:** Reproducibility không có nghĩa là commit mọi file runtime; cần commit source, manifest và evidence ổn định, còn index có thể tái tạo.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:** Crossref raw data được Vân clean thành contract cho index. Sau đó build MiniLM/Chroma collection; Đức dùng test set có stable IDs để evaluate. Quality đo null/duplicate/validity, freshness đo publication staleness. Corruption flow dùng lại test set và tách index để impact có thể so sánh. Repair reload raw snapshot, rebuild lại chứ không chỉnh metric. Thành công được chứng minh bởi repair lineage pass, quality/freshness pass và bốn evaluation metrics phục hồi về baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét cá nhân                                                                        |
| ---------------------- | -------: | --------: | -------: | ------------------------------------------------------------------------------------------- |
| `retrieval_hit_rate` |   1.0000 |    0.6667 |   1.0000 | Isolated corrupted collection cho thấy document loss/content defects làm retrieval giảm. |
| `mean_token_f1`      |   1.0000 |    0.5141 |   1.0000 | Corruption content làm answers lệch ground truth.                                         |
| `judge_accuracy`     |   1.0000 |    0.5833 |   1.0000 | Repair source-based phục hồi correctness.                                                 |
| `mean_judge_score`   |   5.0000 |    3.5000 |   5.0000 | So sánh ba-state có delta rõ ràng.                                                      |
| Quality checks         |     Pass |      Fail |     Pass | Corrupted có duplicate ID, blank summary, duplicate row.                                   |
| Freshness status       |    Fresh |     Stale |    Fresh | Make-publication-stale tạo 2 stale rows.                                                   |

### Kết luận từ số liệu

1. Corruption có log → quality/freshness fail và corrupted index khác baseline → mọi primary metric giảm trên test set không đổi.
2. Reload raw snapshot + rebuild clean/index → lineage pass, quality/freshness pass → mọi metric bằng baseline.

Kịch bản ảnh hưởng rõ nhất về observability là stale publication: nó tạo ngay 2 stale rows và freshness đổi Fresh → Stale. Về RAG, drop document cùng blank/noisy/truncated content làm retrieval/answer score giảm. Điều khác kỳ vọng là final row count vẫn 24; quality/lineage cho thấy duplicate rows đã che count difference.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Orchestration phải bảo vệ baseline bằng isolation và guards trước khi chạy corruption.
2. Corruption có giá trị khi có event log, expected signal và measured impact.
3. Repair chỉ đáng tin khi replay từ raw source kèm lineage, không phải chỉnh output.

### Nếu có thêm thời gian

Tôi sẽ thêm end-to-end tests chạy ba-state flow trong temporary Chroma directory, assert baseline hashes, collection counts và report deltas tự động.

## 10. Cam kết của thành viên

- [X] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [X] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [X] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [X] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [X] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [X] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Hà Duyên Hùng
**Ngày xác nhận:** 2026-08-06
