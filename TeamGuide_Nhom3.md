# Hướng dẫn chi tiết cho Nhóm 3 thành viên — Day 10 Data Pipeline & Data Observability

> Tài liệu này tổng hợp từ `README.md`, `Guide.md`, `Rubric.md`, `report/README.md` và timer `phan-cong-day-10-data-pipeline-4h.html` (chọn "Nhóm 3"), viết riêng cho một nhóm **3 người** với mốc thời gian 4 giờ. Đọc một lần trước khi bắt đầu, dùng như checklist trong suốt buổi làm.

## 0. Lưu ý quan trọng: khác biệt giữa hai nguồn phân công

`report/README.md` (dùng để chấm báo cáo) và file timer HTML chia vai trò nhóm 3 **không giống nhau**:

| Nguồn | Vai trò 1 | Vai trò 2 | Vai trò 3 |
|---|---|---|---|
| `report/README.md` (chính thức cho báo cáo) | Ingestion & Cleaning owner (`crossref.py`, `cleaning.py`) | Evaluation & Observability owner (`testset.py`, `quality.py`, `reporting.py`) | Corruption & Integration owner (`corruption.py`, `phase1.py`, `corruption_flow.py`) |
| Timer HTML (nhóm 3) | Data foundation & pipeline: ingestion + cleaning + **repair + orchestration** | RAG & evaluation: index/agent + test set/metrics | Observability & reporting một mình |

**Guide này đi theo `report/README.md`** vì `individual_report.md`/`group_report.md` — thứ sẽ được chấm — dùng đúng 3 vai trò đó làm cột "owner". Nếu nhóm bạn mở file HTML để chạy timer, cứ dùng đồng hồ đếm giờ và các checkpoint (CP0–CP6) của nó bình thường, chỉ **bỏ qua cách nó gộp vai trò** và áp theo bảng phân công ở Mục 1 dưới đây.

## 1. Phân công vai trò (theo `report/README.md`)

| Thành viên | Vai trò chính | File sở hữu | Output bàn giao |
|---|---|---|---|
| **TV1** | Data ingestion & cleaning owner | `src/ingestion/crossref.py`, `src/ingestion/cleaning.py` | Raw records, cleaned dataset, mô tả cleaning rules |
| **TV2** | Evaluation & observability owner | `src/evaluation/testset.py`, `src/observability/quality.py`, `src/observability/reporting.py` | Evaluation set, quality/freshness results, report functions |
| **TV3** | Corruption & integration owner | `src/ingestion/corruption.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` | Baseline/corrupted/repaired artifacts, metrics, comparison report |

Ghi chú từ `report/README.md`: với nhóm 3, khối tích hợp của **TV3 khá nặng** (2 pipeline orchestration + corruption). TV1 hỗ trợ kiểm tra dữ liệu repair, TV2 hỗ trợ xác minh metrics và report cho TV3. Đây không phải việc phụ — hãy chủ động dành thời gian ở CP5/CP6 để hỗ trợ thay vì coi đó là việc riêng của TV3.

`src/retrieval/` (embeddings, index, agent, llm, qa) đã có code tham khảo — không ai "sở hữu" riêng, cả 3 người đều cần đọc hiểu để dùng, chủ yếu TV3 sẽ chạm vào nhiều nhất khi build baseline/corrupted/repaired index.

## 2. Nguyên tắc xuyên suốt — đọc một lần, áp dụng cả buổi

- Chỉ chạy corruption flow **sau khi** baseline đã tạo đủ artifact.
- Giữ nguyên **test set, ground truth, evaluator, top-k** khi so sánh baseline/corrupted/repaired — đổi bất kỳ thứ nào trong số này làm so sánh vô nghĩa.
- Dùng **path và collection riêng** cho 3 trạng thái (`papers-baseline`, `papers-corrupted`, `papers-repaired`) — không ghi đè baseline.
- Repair bằng cách **chạy lại từ raw/source đáng tin**, không sửa tay answers hoặc metrics.
- Report phải trỏ tới artifact thật; **không commit `.env` hoặc API key**.
- Mọi filter/dedupe/corruption phải để lại **log hoặc count** — không làm mất record âm thầm.

## 3. Luồng end-to-end cần chứng minh bằng artifact

```text
Crossref API
    -> raw response / raw records        (data/raw/)
    -> cleaned dataset                    (data/clean/)
    -> embedding + ChromaDB index         (data/embeddings/, collection papers-baseline)
    -> evaluation baseline                (data/eval/, data/results/baseline_metrics.json)
    -> quality/freshness reports          (data/quality/, data/reports/phase1_report.md)
    -> corrupt data                       (papers-corrupted, data/results/corruption_log.json)
    -> evaluate impact                    (corrupted metrics)
    -> repair từ raw                      (papers-repaired)
    -> so sánh baseline/corrupted/repaired (data/reports/corruption_report.md)
```

## 4. Lịch trình 4 giờ theo checkpoint

Tổng phiên **04:00**, nghỉ **15 phút** lúc 02:00–02:15. Có thể dùng file `phan-cong-day-10-data-pipeline-4h.html` làm đồng hồ đếm ngược cho từng mốc (mở file, chọn "Nhóm 3", dùng phím Space/←/→/R).

### CP0 · 00:00–00:30 (30 phút) — Khởi động, contract & ingestion raw

**Lệnh kiểm tra:** `rg -n "TODO\(student\)|NotImplementedError" src` rồi sau khi fetch lần đầu: `ls data/raw`
**Tiêu chí đạt:** raw response và raw records JSON tồn tại; `PaperRecord` có `paper_id` ổn định; mỗi người biết rõ artifact mình bàn giao.

- **TV1:** Đọc `PaperRecord` schema và Crossref payload, xác định field tạo `paper_id` ổn định (thường theo DOI). Implement `parse_crossref_payload` + fetch/load trong `crossref.py` theo `Settings`. Lưu raw API response (trước parse) **và** raw records đã parse vào `data/raw/`; thêm retry/backoff cho lỗi 429/503.
- **TV2:** Đọc `testset.py`, `quality.py`, `reporting.py` để hiểu trước format cần tạo ra ở các bước sau. Liệt kê artifact bắt buộc phải có sau baseline & corruption flow. Phác thảo các quality/freshness signal sẽ đo (row count, null, duplicate, `age_days`).
- **TV3:** Chốt ownership, branch, definition of done, tên/path artifact cho từng bước. Kiểm tra Python 3.11–3.13 và cài môi trường chạy được (`uv sync` hoặc `pip install -e .`), tạo `.env` từ `.env.example`. Vẽ sơ đồ handoff raw → clean → index → evaluate → corrupt → repair → report để cả nhóm thống nhất.

⚠️ Nếu Crossref lỗi tạm thời (429/503), dùng retry/backoff — không bỏ raw response hay bịa dữ liệu.

### CP1 · 00:30–01:05 (35 phút) — Cleaning, data model & quality gates

**Lệnh:** `ls data/clean`
**Tiêu chí đạt:** clean CSV/JSON đọc được; `paper_id` unique; `text_for_embedding` và `age_days` có mặt; số record bị loại và lý do có thể truy vết.

- **TV1:** Implement `cleaning.py`: normalize title/summary/authors/categories, parse published date. Dedupe theo `paper_id`, tính `age_days`, build `text_for_embedding`. Ghi log/count lý do record bị loại hoặc dedupe; bàn giao sample record + đường dẫn cho TV2/TV3.
- **TV2:** Bắt đầu implement `quality.py` (check row count, `paper_id` unique, title/summary missing, duplicate) và chạy thử ngay trên bản clean đầu tiên của TV1. Chuẩn bị draft câu hỏi cho `testset.py` dựa trên vài record đại diện (chưa chốt vì schema có thể còn đổi). Freshness nên tính từ `published`/`age_days` thật, không giả định ngày hiện tại.
- **TV3:** Review cùng TV1 raw count → clean count; nếu bất thường, ghi thành blocker kèm bằng chứng thay vì tự sửa số. Dựng khung `phase1.py` theo thứ tự raw→clean→index→test set→evaluate→quality→report (chưa chạy được, còn thiếu index/test set). Không cho index/test set chạy trước khi clean schema ổn định.

⚠️ Mọi filter/dedupe phải để lại log — đừng làm mất record âm thầm.

### CP2 · 01:05–01:35 (30 phút) — Test set, RAG index & agent smoke test

**Lệnh:** `find data -maxdepth 2 -type f | sort` (Windows PowerShell: `Get-ChildItem data -Recurse -Depth 1 -File`)
**Tiêu chí đạt:** `test_set.json`, embedding manifest và collection baseline tồn tại; semantic search, exact lookup và agent đều trả lời có nguồn.

- **TV1:** Xác minh không còn `text_for_embedding` rỗng hay `paper_id` trùng trong bản clean cuối. Đối chiếu với `embeddings.py`/`index.py` để confirm input schema (`paper_id`, `title`, `content`, metadata) khớp clean output. Đứng sẵn hỗ trợ TV3 nếu build index báo thiếu field.
- **TV2:** Implement `build_test_set` trong `testset.py`: mỗi sample có `id`, `question_type`, `question`, `ground_truth`, `ground_truth_doc_ids` — lấy ID từ `paper_id` clean thật, không tự bịa. Lưu test set cố định vào `data/eval/`, đọc thử vài row. Đọc `qa.py`/`metrics.py` để hiểu format answer và metric sẽ tính ở CP3.
- **TV3:** Build MiniLM embeddings + Chroma collection `papers-baseline` từ clean data (dùng code tham khảo `embeddings.py`/`index.py`). Test `semantic_search` và lookup theo `paper_id`/title; build `agent.py`, đảm bảo agent gọi tool trước khi trả lời câu hỏi factual. Nếu smoke test không tìm thấy tài liệu, sửa contract index/clean trước — không mang collection lỗi sang evaluation.

### CP3 · 01:35–02:00 (25 phút) — Baseline end-to-end & báo cáo

**Lệnh:** `uv run python script/run_phase1.py` (hoặc `python script/run_phase1.py` nếu dùng pip)
**Tiêu chí đạt:** `baseline_metrics.json`, answers, quality/freshness report, `data/reports/phase1_report.md` tồn tại; nhóm giải thích được ít nhất một hit/miss bằng artifact thật.

- **TV1:** Kiểm tra clean schema, `age_days`, `text_for_embedding` trong artifact vừa sinh ra khớp thiết kế. Xác minh quality check phản ánh dữ liệu thật (không hard-code pass). Nếu phát hiện lỗi contract, sửa `cleaning.py` rồi phối hợp TV3 chạy lại baseline.
- **TV2:** Run evaluator (qua `phase1.py`) để tạo answers và `baseline_metrics.json`. Run quality checks + freshness report + `generate_phase1_report`. Đọc một hit và một miss cụ thể, đối chiếu report với JSON/CSV thật; chuẩn bị giải thích `retrieval_hit_rate`, `mean_token_f1`, `judge_accuracy`, `mean_judge_score`.
- **TV3:** Hoàn thiện `phase1.py` (raw→clean→index→test set→evaluate→quality→freshness→report) và chạy `script/run_phase1.py` end-to-end. Ghi lại traceback/blocker nếu fail; kiểm tra path/artifact thật trước khi coi baseline "xong" — không chỉ nhìn exit code 0. Chốt baseline làm mốc so sánh trước giờ nghỉ.

⚠️ Baseline chỉ hoàn tất khi artifacts, metrics và report **khớp nhau** — không phải chỉ khi script chạy không lỗi.

### CP4 · 02:00–02:15 (15 phút) — Nghỉ

Trước khi nghỉ: TV3 ghi lại baseline checklist + 1 blocker còn lại (nếu có). Sau khi quay lại, cả nhóm nên đã hình dung sẵn: corruption scenario nào sẽ dùng, raw source nào để repair, quality/freshness signal nào kỳ vọng sẽ đổi.

### CP5 · 02:15–03:15 (60 phút) — Corruption có kiểm soát & đo impact

**Lệnh:** `uv run python script/run_corruption_flow.py`
**Tiêu chí đạt:** corruption log, corrupted clean/index/answers/metrics/quality đầy đủ; **baseline không bị ghi đè**.

- **TV1:** Xác nhận raw source nguyên vẹn trước khi corrupt (đây là điểm khôi phục dùng ở CP6). Hỗ trợ TV3 chọn record có lineage rõ để corrupt (dễ chứng minh repair sau này). Sau khi có corrupted dataset, review lại: nó khác baseline đúng như log mô tả không.
- **TV2:** Evaluate corrupted dataset bằng đúng test set cũ, tạo answers/metrics corrupted. So metric/answer corrupted với baseline, tìm ít nhất một case xấu đi có bằng chứng cụ thể. Run quality/freshness cho corrupted dataset, lưu report riêng; chỉ nối corruption log với quality signal/metric change khi có bằng chứng — không kết luận vượt quá số liệu.
- **TV3:** Implement `corruption.py` — xóa một số latest records, blank summary, add noise vào summary, truncate title, làm stale publication date, add duplicate rows — log record ID, loại lỗi, tham số, before/after count cho từng corruption. Implement `corruption_flow.py`: corrupt → rebuild index (collection `papers-corrupted` riêng) → evaluate → quality/freshness. Đảm bảo output dùng path/collection riêng, không ghi đè baseline; nếu phát hiện data contract sai, sửa gốc thay vì vá JSON kết quả.

⚠️ Lỗi dữ liệu phải có chủ đích, có log và đo được tác động — không tạo corruption chỉ để có file.

### CP6 · 03:15–04:00 (45 phút) — Repair từ raw, comparison, review & demo

**Lệnh:** `ls data/results/repaired_metrics.json data/reports/corruption_report.md` (PowerShell: `Test-Path data/results/repaired_metrics.json`, `Test-Path data/reports/corruption_report.md`)
**Tiêu chí đạt:** repaired artifacts và comparison report có đủ baseline–corrupted–repaired + delta; repo không có secret; demo dùng artifact thật.

- **TV1:** Re-run cleaning từ raw để tạo repaired dataset — **không** copy/sửa tay từ baseline. Kiểm tra repaired schema, row count, quality signals hồi phục đúng kỳ vọng. Chứng minh record bị corrupt/drop đã phục hồi bằng lineage/raw evidence; hỗ trợ kiểm tra `.env`/API key không lọt vào Git.
- **TV2:** Evaluate repaired bằng test set cũ, tính delta giữa baseline/corrupted/repaired cho `retrieval_hit_rate`, `mean_token_f1`, `judge_accuracy`, `mean_judge_score`. Generate comparison report (`data/reports/corruption_report.md`) từ metrics/quality/freshness thật; nêu rõ nếu recovery chưa hoàn toàn. Chuẩn bị một case hit/miss tiêu biểu để demo trung thực.
- **TV3:** Điều phối repair/comparison trong `corruption_flow.py`, freeze scope, chia phần demo. Chạy checklist cuối: đủ artifact, report khớp output, không secret/không hard-code path. Chỉ công bố "phục hồi" khi số liệu và report thực sự chứng minh điều đó.

⚠️ Ưu tiên bằng chứng — report phải khớp artifact thật, không tô đẹp số liệu để demo.

## 5. Checklist artifact bắt buộc

| Artifact | Đường dẫn |
|---|---|
| Raw response/records | `data/raw/` |
| Cleaned dataset | `data/clean/` |
| Embedding manifest | `data/embeddings/` |
| Evaluation set | `data/eval/` |
| Baseline metrics | `data/results/baseline_metrics.json` |
| Quality/freshness | `data/quality/` |
| Baseline report | `data/reports/phase1_report.md` |
| Corruption log | `data/results/corruption_log.json` |
| Repaired metrics | `data/results/repaired_metrics.json` |
| Comparison report | `data/reports/corruption_report.md` |

## 6. Rubric tóm tắt (đối chiếu `Rubric.md` để biết chi tiết)

Tổng điểm cơ bản 0–90, bonus 90–100 (chỉ tính khi đã đạt ≥90):

| Mục | Điểm | Liên quan vai trò |
|---|--:|---|
| Code structure & organization | 10 | Cả nhóm |
| Raw data ingestion | 15 | TV1 |
| Cleaning & data modeling | 15 | TV1 |
| Embedding & vector store | 10 | TV3 (dùng code tham khảo) |
| Agent & multi-provider LLM | 10 | TV3 |
| Evaluation & scoring | 10 | TV2 |
| Data observability | 10 | TV2 |
| Corruption & comparison | 10 | TV3 |

Trừ điểm nếu: không chạy được end-to-end, thiếu file quan trọng, hard-code path/key, hoặc báo cáo không khớp artifact thực tế.

## 7. Nộp bài

- 1× `report/group_report.md` cho cả nhóm — điền số liệu thật, không để `[ ]` trống.
- 3× `report/individual_report.md` — mỗi người tự viết, không sao chép của nhau; nếu cần lưu song song trong repo, đặt tên `<MSSV>_HoTen.md`.
- Đối chiếu `report/README.md` mục 8 "Definition of Done" và `Rubric.md` trước khi nộp.
- Kiểm tra lại: không có `.env`, API key, token trong source/report/log/ảnh.
