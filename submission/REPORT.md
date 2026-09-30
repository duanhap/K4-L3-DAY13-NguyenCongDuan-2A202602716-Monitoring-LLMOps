# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Công Duẩn
- **MSSV:** 2A202602716
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/duanhap/K4-L3-DAY13-NguyenCongDuan-2A202602716-Monitoring-LLMOps
- **Commit SHA cuối:** 8a23c963a7943d244e999cc5a6874f35a8f68f7b
- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-2A202602716`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | **100/100** | Sau CP1: correlation ID, enrichment, PII scrub đều pass |
| `validate_dashboard.py` | 6/6 | **6/6** | Contract YAML hợp lệ; runtime dashboard tại `dashboard.html` |
| `pytest` | 22 passed | **24 passed** | Tất cả pass sau khi fix `summarize_text` max_len |
| Số traces hợp lệ | 0 | **≥ 10 traces** | Xem `evidence/06-trace-list.png` trong project `day13-k4-l3b-2A202602716` |
| Số PII leak | 0 | **0** | `validate_logs.py` xác nhận 0 PII leak |
| Latency P95 / TTFT P95 (baseline) | — | **156 ms / 51 ms** | Đo trên load test bình thường |
| Latency P95 / TTFT P95 (challenge) | — | **2652.8 ms / 50 ms** | Khi `rag_slow` bật; TTFT không đổi → retrieval là bottleneck |
| Retrieval success rate | — | **100%** | `tool_success=true` trên toàn bộ request |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** Middleware nhận `x-request-id` hợp lệ hoặc sinh `req-<8-hex>`, bind vào structlog context và trả về header.
- **Các metadata được ghi vào structured log:** Handler bind `user_id_hash`, `session_id`, `feature`, `model`, `env`; correlation ID được bind ở middleware.
- **Cách bảo đảm PII được scrub trước khi ghi:** Processor đệ quy scrub mọi chuỗi trong event trước JSONL file writer; baseline trước sửa có 0 PII leak theo validator.
- **Cách kiểm chứng kết quả:** CP0 baseline `validate_logs.py` 30/100; học viên xác nhận CP1 đạt 100/100 và các test PII/validator pass.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Đã xác nhận trên Langfuse; nhiều traces xuất hiện trong project cá nhân.
- **Cấu trúc root/retrieval/generation observations:** Root `lab-agent-run`; child `retrieval` span ghi query đã sanitize, documents/count và tool status; child `generation` ghi model, prompt metadata, usage, cost và completion preview. Waterfall đã được xác nhận live.
- **Cách nối trace với log:** Middleware tạo/nhận `correlation_id`; ID này được ghi trong structured logs và metadata root trace. Dùng ID để đối chiếu log `response_sent` với trace rồi xem waterfall của `retrieval`/`generation`.
- **Prompt name:** `day13-chat`.
- **Version/label baseline:** Version 1, labels `baseline` và `production`.
- **Version/label candidate:** Version 2, label `candidate`.
- **Trace ID của mỗi version:** Xem trace metadata trong `evidence/08a-trace-metadata.png` và `evidence/08b-trace-metadata.png`; nếu báo cáo cần ID dạng text, bổ sung trực tiếp từ trace detail Langfuse.
- **Cách promote và rollback `production`:** Đã promote label `production` sang version 2 rồi rollback về version 1; evidence ở `evidence/10a-prompt-rollback.png` và `evidence/10b-prompt-rollback.png`.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** Script `scripts/generate_dashboard.py` đọc `data/logs.jsonl` và sinh `dashboard.html` với đủ 6 panel: Latency/TTFT (P50/P95/P99 + TTFT P95), Traffic (req/min), Errors & Retrieval Success, Cost (USD), Tokens (in/out), Quality Score. Time range mặc định 60 phút, refresh 30 giây, mỗi panel có threshold/SLO line.
- **SLO và lý do chọn:** 99.5% request thành công trong ≤ 3000 ms theo cửa sổ 28 ngày. Ngưỡng 3000 ms đủ chặt để phát hiện retrieval degradation (baseline P95 ~156 ms) mà không gây false alarm khi tải nhẹ.
- **Cách tính error budget:** `100% − 99.5% = 0.5%`; với 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn ngưỡng SLO. Xem chi tiết tại `config/slo.yaml`.
- **Ba alert và runbook tương ứng:** `HighLatencyP95` (P95 > 3000 ms trong 5 phút), `HighRequestErrorRate` (lỗi > 2% trong 5 phút), `LowQualityScore` (mean quality < 0.75 trong 10 phút); cấu hình đầy đủ tại `config/alert_rules.yaml`, runbook 3 bước tại `docs/alerts.md`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Khoảng thời gian điều tra:** `2026-09-30T08:29:40Z` – `2026-09-30T08:29:54Z` (UTC)
- **Triệu chứng từ metrics:** Latency P95 đạt **2652.8 ms**, vượt ngưỡng riêng của challenge **2000 ms**; giá trị này vẫn thấp hơn SLO chung **3000 ms**. TTFT P95 là 50 ms, nên generation không có dấu hiệu chậm tương ứng. Cả 5 request feature `monitoring` đều có latency khoảng 2652–2653 ms.
- **Log line và correlation ID liên quan:**
  - Request chậm nhất: `correlation_id=req-3fca2e96`, `latency_ms=2653`, `ts=2026-09-30T08:29:53.853306Z`
  - Log `request_received`: `ts=2026-09-30T08:29:51.199167Z` → `response_sent`: `ts=2026-09-30T08:29:53.853306Z` → delta = **2654 ms**
  - Tất cả 5 correlation IDs bị ảnh hưởng: `req-97620868`, `req-95e9f068`, `req-4dc33d0a`, `req-0732a9d4`, `req-3fca2e96`
  - Xem: ![Incident log](evidence/13-incident-log.png)
- **Trace ID và span gây ảnh hưởng:** Trace ID `03e2ecb12a6015adc2660a3d6e9eaebe`, correlation ID `req-3fca2e96`. Langfuse waterfall ghi tổng ~2.65 s, retrieval ~2.50 s, generation ~152 ms. Xem: ![Incident trace](evidence/14-incident-trace.png)
- **Root cause:** Incident `rag_slow` được kích hoạt làm hàm `retrieve()` trong `app/mock_rag.py` sleep 2.5 giây trước khi trả về documents. TTFT không bị ảnh hưởng (token đầu tiên từ LLM vẫn nhanh) vì bottleneck nằm hoàn toàn ở bước RAG retrieval, trước khi LLM bắt đầu generate. Tín hiệu chẩn đoán: latency tổng tăng ~17x, TTFT không đổi → retrieval là span chậm.
- **Fix action:** Tắt incident bằng `POST /incidents/rag_slow/disable` (hoặc `python scripts/inject_incident.py --disable`). Trong production: kiểm tra kết nối vector store, timeout configuration, và circuit breaker của retrieval service.
- **Preventive measure:**
  1. Alert `HighLatencyP95` kích hoạt khi P95 > 3000 ms trong 5 phút → tự động page on-call qua Slack `#k4-l3b-alerts`.
  2. Thêm timeout riêng cho retrieval span (ví dụ 1 giây); nếu timeout thì fallback về cached docs hoặc phản hồi không có context thay vì block toàn bộ request.
  3. Tách metric `retrieval_latency_ms` riêng biệt (hiện nay chỉ có `latency_ms` tổng) để alert sớm hơn khi chỉ retrieval chậm.
  4. Runbook tại `docs/alerts.md`: metric spike → lọc log theo `correlation_id` → mở trace waterfall → kiểm tra retrieval span duration → tắt incident hoặc rollback config.

> Evidence chuỗi đầy đủ: ![Incident metric](evidence/12-incident-metric.png) → ![Incident log](evidence/13-incident-log.png) → ![Incident trace](evidence/14-incident-trace.png)

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Giữ ngưỡng SLO chung 3000 ms theo contract, đồng thời thêm chế độ dashboard `Challenge feature` với ngưỡng challenge 2000 ms. Cách này làm rõ cảnh báo sớm của bài thực hành mà không thay đổi SLO vận hành chung.
- **Một lỗi/blocker đã gặp:** Trace ban đầu chưa xuất hiện trên Langfuse và prompt label `production` vẫn được dùng dù đã đổi biến môi trường.
- **Cách tìm nguyên nhân và xử lý:** Đối chiếu trạng thái server, request load test, metadata `prompt_label`/`prompt_version` trên trace; phân biệt log server với thời gian chờ phía client khi chạy concurrency; khởi động lại API sau thay đổi cấu hình và xác nhận trace mới trong đúng project.
- **Cách hiểu luồng Metrics → Logs → Traces:** Dashboard phát hiện P95 vượt ngưỡng; correlation ID tìm request tương ứng trong JSONL; cùng ID trong metadata trace mở ra waterfall để xác định span retrieval chậm; cuối cùng ghi root cause, hành động xử lý và biện pháp phòng ngừa.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** Version/label giúp kiểm soát prompt đang chạy và rollback nhanh; token/cost đo hiệu quả; SLO và error budget lượng hóa độ tin cậy; trace cho phép quy nguyên nhân theo từng request.
- **Điều quan trọng nhất đã học:** Không kết luận từ một con số tổng hợp duy nhất; phải nối metric, log và trace qua cùng correlation ID, đồng thời phân biệt ngưỡng cảnh báo sớm với SLO chính.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**
  - Dashboard là file HTML tĩnh sinh từ script, không phải live server — cần chạy `python scripts/generate_dashboard.py` để refresh. Trong production nên dùng Grafana hoặc Streamlit với auto-refresh thật sự.
  - Child observation `retrieval_latency_ms` chưa được tách thành metric riêng trong Prometheus/log — hiện chỉ suy ra từ trace waterfall.
  - Chỉ có 5 queries trong challenge nên sample size nhỏ; P95 tính trên ít điểm có thể không ổn định.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối — `8a23c963a7943d244e999cc5a6874f35a8f68f7b`.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối — 14 file evidence đặt trong `submission/evidence/`, dẫn bằng `evidence/xx-name.png`.
- [x] Incident evidence nối đúng metric → log → trace — `12-incident-metric.png` (P95 spike) → `13-incident-log.png` (`correlation_id=req-3fca2e96`, latency=2653ms) → `14-incident-trace.png` (retrieval span ~2500ms).
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân `day13-k4-l3b-2A202602716` — ảnh 06–10 và 14 lấy từ đúng project; không lộ API key/secret.
- [x] Repository chạy lại được theo README — `pip install -r requirements.txt`, `uvicorn app.main:app --reload --env-file .env`, `python scripts/load_test.py`.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác — `.env` trong `.gitignore`, `config/challenge.json` trong `.gitignore`, không commit `.venv/`.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs — **cần nộp thủ công trên VLearn sau khi push commit cuối**.
