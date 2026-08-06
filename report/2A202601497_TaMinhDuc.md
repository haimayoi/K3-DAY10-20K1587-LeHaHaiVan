# Báo cáo cá nhân — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                                                             |
| ------------------ | --------------------------------------------------------------------- |
| Họ và tên       | Tạ Minh Đức                                                        |
| MSSV               | 2A202601497                                                           |
| Khóa/Lớp         | E402                                                                  |
| Tên nhóm         | B6                                                                    |
| Vai trò chính    | Evaluation và observability owner                                    |
| Repository         | https://github.com/haimayoi/K3_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06                                                            |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable   | File/hàm phụ trách              | Input nhận vào                      | Output bàn giao                        | Trạng thái |
| -------------------- | ---------------------------------- | ------------------------------------- | --------------------------------------- | ------------ |
| Fixed evaluation set | `src/evaluation/testset.py`      | Clean dataframe                       | 12 câu hỏi có ground-truth IDs thật | Hoàn thành |
| Quality/freshness    | `src/observability/quality.py`   | Baseline/corrupted/repaired dataframe | Quality và freshness JSON              | Hoàn thành |
| Reporting            | `src/observability/reporting.py` | Metrics, quality, freshness           | Baseline/comparison Markdown reports    | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                                         | Thành viên/module được hỗ trợ | Kết quả                                                              |
| ---------------------------------------------------- | ------------------------------------ | ---------------------------------------------------------------------- |
| Xác minh fixed-set evaluation cho corruption/repair | Hùng,`corruption_flow.py`         | Ba trạng thái dùng chung`data/eval/test_set.json`                 |
| Đối chiếu report với JSON artifacts              | Vân, Hùng                          | Comparison report phản ánh đúng metric/quality/freshness thực tế |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện      | File/hàm/artifact liên quan               | Kết quả bàn giao                                         | Cách xác minh                                                |
| -------------------------------- | ------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------- |
| Tạo test set từ clean data     | `testset.py`, `data/eval/test_set.json` | 12 factual samples thuộc 4 question types                  | Mọi`ground_truth_doc_ids` là `paper_id` thật            |
| Chạy quality/freshness          | `quality.py`, `data/quality/*.json`     | Bảy quality checks và freshness state cho ba trạng thái | Baseline pass/fresh, corrupted fail/stale, repaired pass/fresh |
| Tạo report bằng artifact thật | `reporting.py`, `data/reports/*.md`     | Phase-1 report và comparison report có delta              | Đọc Markdown đối chiếu JSON metrics/quality/freshness     |

Output tiêu biểu là `data/reports/corruption_report.md`. Báo cáo đặt baseline, corrupted và repaired cạnh nhau: bốn metrics có delta, quality status, failed checks, row count, freshness và stale rows. Vì vậy recovery không được kết luận từ một metric đơn lẻ.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Evaluation phải dùng câu hỏi factual, ground-truth document IDs có thể kiểm chứng, và cùng một bộ test cho cả ba data states. Nếu test set thay đổi giữa các lần chạy, metric không còn so sánh công bằng. Ngoài ra cần có signals giải thích tại sao metric thay đổi.

### Cách triển khai

`build_test_set` chọn các clean records theo thứ tự ổn định và tạo các câu hỏi summary/date/authors/categories. ID được lấy trực tiếp từ `paper_id`; title được đặt trong câu hỏi để QA layer có thể exact lookup. Quality module báo counts thay vì âm thầm bỏ record lỗi. Freshness dùng `published` và `age_days` thực tế, không thay đổi theo ngày giả định. Reporting chỉ đọc các artifact đã tạo để sinh bảng Markdown.

### Input, output và contract

| Thành phần                   | Mô tả                                                                                          |
| ------------------------------ | ------------------------------------------------------------------------------------------------ |
| Input                          | Clean dataframe, metrics JSON, answers JSON, quality/freshness results                           |
| Output                         | Fixed test set; baseline/corrupted/repaired quality/freshness JSON; Markdown reports             |
| Module phụ thuộc             | `cleaning.py`, `metrics.py`, `retrieval/index.py`, `core/config.py`                      |
| Module sử dụng output        | `phase1.py`, `corruption_flow.py`, group/individual reports                                  |
| Điều kiện lỗi cần xử lý | Clean data thiếu required columns, test set rỗng, thiếu`paper_id`, invalid freshness fields |

### Cách xác minh

```bash
py -3.11 script/run_phase1.py
py -3.11 script/run_corruption_flow.py
py -3.11 -m pytest -q
```

- **Kết quả mong đợi:** Cùng test set được dùng ba lần; JSON/report tồn tại; corrupted signal và metrics xấu đi; repaired phục hồi.
- **Kết quả thực tế:** 12 samples; baseline/repaired metrics đều 1.0000 và judge score 5; corrupted metrics lần lượt 0.6667, 0.5141, 0.5833, 3.5000.
- **Artifact/log:** `data/eval/test_set.json`, `data/quality/*.json`, `data/reports/phase1_report.md`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần so sánh ảnh hưởng corruption và hiệu quả repair một cách công bằng.
- **Các phương án đã cân nhắc:** Tạo test set mới ở mỗi state; dùng một test set cố định từ baseline clean data.
- **Phương án đã chọn:** Dùng `data/eval/test_set.json` cố định cho baseline, corrupted và repaired.
- **Lý do:** Nếu câu hỏi/ground truth thay đổi, metric change không thể quy cho corruption hay repair. Fixed set tạo controlled comparison.
- **Bằng chứng quyết định phù hợp:** Comparison report cho thấy mọi metric giảm ở corrupted và quay về baseline ở repaired trên đúng 12 samples đó.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Một bảng comparison chỉ hiển thị quality/freshness của corrupted và repaired sẽ thiếu baseline để chứng minh recovery hoàn toàn.
- **Lệnh hoặc bước tái hiện:** Đọc `data/results/baseline_metrics.json`, `corrupted_metrics.json`, `repaired_metrics.json` cùng các quality/freshness JSON rồi kiểm tra report.
- **Nguyên nhân gốc:** Performance metrics và data signals phải được đặt trong cùng ba-state frame; thiếu baseline làm phần kết luận không đủ evidence.
- **Cách xử lý:** Report generator hiển thị Baseline/Corrupted/Repaired, corrupted-baseline delta và repaired-corrupted delta; bổ sung failed quality checks và freshness signals.
- **Cách xác minh sau khi sửa:** `data/reports/corruption_report.md` có đầy đủ các cột và khớp JSON artifacts.
- **Điều học được:** Observability report là evidence layer; format report cần giữ nguyên ngữ cảnh metric, không chỉ hiển thị output cuối.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:** Sau cleaning, `text_for_embedding` được index vào Chroma bằng MiniLM. Test set dùng `paper_id` thật để kiểm tra retrieved IDs và answer content. Quality checks đo completeness/uniqueness/validity của dataframe, còn freshness đo độ cũ publication theo `age_days` và ngưỡng 180 ngày. Baseline/corrupted/repaired phải dùng cùng test set để thay đổi metrics phản ánh data state. Repair thành công khi lineage từ raw pass, quality/freshness pass và metrics quay lại baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét cá nhân                                                |
| ---------------------- | -------: | --------: | -------: | ------------------------------------------------------------------- |
| `retrieval_hit_rate` |   1.0000 |    0.6667 |   1.0000 | Đúng document bị mất/biến dạng làm retrieval giảm.          |
| `mean_token_f1`      |   1.0000 |    0.5141 |   1.0000 | Blank/noisy summary làm answer token overlap giảm.                |
| `judge_accuracy`     |   1.0000 |    0.5833 |   1.0000 | Answer correctness giảm theo data quality.                         |
| `mean_judge_score`   |   5.0000 |    3.5000 |   5.0000 | Rebuild source data phục hồi score tối đa.                      |
| Quality checks         |     Pass |      Fail |     Pass | Corrupted fail: duplicate IDs, missing summaries, exact duplicates. |
| Freshness status       |    Fresh |     Stale |    Fresh | Có 2 stale rows trong corrupted, repaired là 0.                   |

### Kết luận từ số liệu

1. Corruption → uniqueness/completeness/freshness fail → retrieval và answer metrics giảm trên fixed set.
2. Repair từ raw snapshot → quality/freshness recovery → bốn metrics quay lại baseline.

Corruption rõ nhất là blank summary kết hợp duplicate rows: nó không chỉ làm summary check fail mà còn làm nhiều bản sao lỗi xuất hiện, góp phần làm answer quality giảm. Kết quả không kỳ vọng là row count corrupted vẫn bằng 24; tôi kiểm tra quality artifact và corruption log để xác định đây là do duplicates bù vào dropped records, không phải corruption không có tác động.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Ground-truth document IDs phải liên kết trực tiếp với clean data.
2. Quality/freshness signals giải thích metric change tốt hơn metric đơn lẻ.
3. Recovery claim cần ba trạng thái cùng test set và evidence từ artifact thật.

### Nếu có thêm thời gian

Tôi sẽ mở rộng test set vượt ba documents, thêm paraphrase/multi-hop queries, và bật Ragas với configuration/output được lưu rõ ràng.

## 10. Cam kết của thành viên

- [X] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [X] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [X] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [X] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [X] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [X] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Tạ Minh Đức
**Ngày xác nhận:** 2026-08-06
