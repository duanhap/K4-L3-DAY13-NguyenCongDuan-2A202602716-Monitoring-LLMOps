# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1 — HighLatencyP95

- Severity: `warning`; duration: `5m`; Slack: `#k4-l3b-alerts`; owner: `student-2A202602716`.
- Condition: P95 `response_sent.latency_ms` > 3000 ms for 5 minutes.
- User impact: replies arrive later than the 3-second latency objective.
- First checks:
  1. Open `/dashboard` and confirm the latency window and P95/P99 values.
  2. Find a slow `response_sent` record in `data/logs.jsonl`; note its `correlation_id`.
  3. Open the matching Langfuse trace and compare retrieval and generation durations.
- Mitigation: roll back the latest prompt/configuration change if evidence links the regression to it; otherwise disable the active practice incident and reduce request concurrency while investigating.

## Alert 2 — HighRequestErrorRate

- Severity: `critical`; duration: `5m`; Slack: `#k4-l3b-alerts`; owner: `student-2A202602716`.
- Condition: `request_failed / request_received > 2%` over a rolling 5-minute window.
- User impact: requests fail instead of returning an answer.
- First checks:
  1. Confirm the errors panel and time range in `/dashboard`.
  2. Inspect `request_failed` records for `error_type`, `correlation_id`, and `tool_success`.
  3. Open one matching trace and identify the failed observation.
- Mitigation: disable the injected incident if active; restore the last known working prompt/configuration and retry one request before resuming the workload.

## Alert 3 — LowQualityScore

- Severity: `warning`; duration: `10m`; Slack: `#k4-l3b-alerts`; owner: `student-2A202602716`.
- Condition: mean `response_sent.quality_score` < 0.75 over a rolling 10-minute window.
- User impact: answers may be less relevant or less complete.
- First checks:
  1. Confirm the quality panel is populated for the alert window.
  2. Compare low-quality response records and their feature, prompt version, and correlation IDs.
  3. Inspect matching traces, especially retrieval documents and the generation observation.
- Mitigation: roll back the production prompt to the last version with acceptable quality; if retrieval is degraded, restore its prior configuration before replaying a small workload.
