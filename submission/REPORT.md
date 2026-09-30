# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Công Duẩn
- **MSSV:** 2A202602716
- **Lớp:** K4-L3B
- **Repository URL:**
- **Commit SHA cuối:**
- **Challenge ID:**
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-<MSSV>`

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
| `validate_logs.py` | 30/100 (105 records; 100 thiếu required fields; 100 thiếu enrichment; 0 correlation ID hợp lệ; 0 PII leak) | 100/100 | Học viên xác nhận sau CP1 |
| `validate_dashboard.py` | 6/6 panel hợp lệ | Chưa chạy sau dashboard runtime update | Cần chạy lại contract validator |
| `pytest` | 22 passed | | `python -m pytest -q` |
| Số traces hợp lệ | Chưa xác nhận trên Langfuse; exporter timeout | | Chưa tính là trace thành công |
| Số PII leak | 0 | | Theo validator hiện tại |
| Latency P95 / TTFT P95 | | | |
| Retrieval success rate | | | |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** Middleware nhận `x-request-id` hợp lệ hoặc sinh `req-<8-hex>`, bind vào structlog context và trả về header.
- **Các metadata được ghi vào structured log:** Handler bind `user_id_hash`, `session_id`, `feature`, `model`, `env`; correlation ID được bind ở middleware.
- **Cách bảo đảm PII được scrub trước khi ghi:** Processor đệ quy scrub mọi chuỗi trong event trước JSONL file writer; baseline trước sửa có 0 PII leak theo validator.
- **Cách kiểm chứng kết quả:** CP0 baseline `validate_logs.py` 30/100; học viên xác nhận CP1 đạt 100/100 và các test PII/validator pass.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Đã xác nhận trên Langfuse; nhiều traces xuất hiện trong project cá nhân.
- **Cấu trúc root/retrieval/generation observations:** Root `lab-agent-run`; child `retrieval` span ghi query đã sanitize, documents/count và tool status; child `generation` ghi model, prompt metadata, usage, cost và completion preview. Waterfall đã được xác nhận live.
- **Cách nối trace với log:**
- **Prompt name:** `day13-chat`.
- **Version/label baseline:** Version 1, labels `baseline` và `production`.
- **Version/label candidate:** Version 2, label `candidate`.
- **Trace ID của mỗi version:** Bổ sung trace ID từ evidence `08a`/`08b` hoặc export Langfuse.
- **Cách promote và rollback `production`:** Đã promote label `production` sang version 2 rồi rollback về version 1; evidence ở `evidence/10a-prompt-rollback.png` và `evidence/10b-prompt-rollback.png`.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** FastAPI dashboard tại `/dashboard`, đọc log JSONL đã scrub; latency P50/P95/P99 + TTFT P95, traffic, errors/retrieval success, cost, tokens và quality; mặc định 60 phút, refresh 30 giây. Cần chụp runtime evidence sau khi mở dashboard.
- **SLO và lý do chọn:** 99.5% request thành công trong ≤3000 ms theo cửa sổ 28 ngày.
- **Cách tính error budget:** `100% - 99.5% = 0.5%`; tối đa 50 request không đạt trên tổng 10,000 request.
- **Ba alert và runbook tương ứng:** `HighLatencyP95` (>3000 ms trong 5 phút), `HighRequestErrorRate` (>2% trong 5 phút), `LowQualityScore` (mean <0.75 trong 10 phút); cấu hình tại `config/alert_rules.yaml`, runbook tại `docs/alerts.md`.

> Ví dụ cách viết error budget: "SLO 99.5% trong 28 ngày nghĩa là error budget 0.5%. Nếu workload có 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn ngưỡng SLO."

## 7. Điều tra challenge

- **Challenge ID:**
- **Khoảng thời gian điều tra:**
- **Triệu chứng từ metrics:**
- **Log line và correlation ID liên quan:**
- **Trace ID và span gây ảnh hưởng:**
- **Root cause:**
- **Fix action:**
- **Preventive measure:**

> Gợi ý cách viết ngắn, không thay cho evidence thực tế: "Metric cho thấy `[latency/error/cost/quality]` bất thường trong `[khoảng thời gian]`. Log line `[event]` có `correlation_id=[...]` đại diện cho request bị ảnh hưởng. Trace cùng `correlation_id` cho thấy span `[retrieval/generation/prompt/tool]` có dấu hiệu `[chậm/lỗi/token tăng]`. Root cause là `[nguyên nhân suy ra từ evidence]`. Fix action là `[hành động khôi phục]`; preventive measure là `[alert/runbook/test/guardrail để ngăn tái diễn]`."

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:** Langfuse exporter timeout; prompt `day13-chat` label `production` trả 404 và app fallback local. CP0 chưa đóng cho đến khi trace mới xuất hiện.
- **Cách tìm nguyên nhân và xử lý:**
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
