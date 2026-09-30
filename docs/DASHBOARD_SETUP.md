# Dựng và kiểm tra dashboard

[`../config/dashboard.yaml`](../config/dashboard.yaml) là contract chấm điểm, không phụ thuộc việc bạn dựng dashboard trong Langfuse hay một công cụ local. File này quy định đúng nguồn dữ liệu, phép tổng hợp, đơn vị và threshold cho sáu panel.

Trường `query` trong YAML là pseudocode mô tả phép tính, không phải câu lệnh để copy nguyên vào mọi công cụ. Bạn chuyển cùng logic đó sang cú pháp của công cụ đã chọn.

Lab không bắt buộc một công cụ dashboard cụ thể. Bạn có thể dùng Streamlit, notebook, Grafana, script local tạo biểu đồ hoặc công cụ tương đương. Điều quan trọng khi chấm là dashboard runtime có dữ liệu thật từ `data/logs.jsonl`, đủ sáu panel, đọc được time range/đơn vị/threshold và khớp logic trong `config/dashboard.yaml`.

## Mapping dữ liệu

| Panel | Event/field | Phép tổng hợp |
|---|---|---|
| Latency | `response_sent.latency_ms/ttft_ms` | latency P50/P95/P99 và TTFT P95 |
| Traffic | `request_received` | count, request/phút |
| Errors | `request_received`, `request_failed`, `error_type`, `tool_success` | error rate, breakdown và retrieval success |
| Cost | `response_sent.cost_usd` | tổng theo phút và toàn cửa sổ |
| Tokens | `response_sent.tokens_in/tokens_out` | tổng theo từng field |
| Quality | `response_sent.quality_score` | mean |

Giữ time range mặc định 60 phút, refresh 30 giây và hiển thị threshold/SLO line. Giá trị chính xác nằm trong `config/dashboard.yaml`; không tự đổi contract chỉ để ảnh dashboard đẹp hơn.

## Cách dựng

1. Hoàn thiện logging/PII và chạy API.
2. Chạy `python scripts/load_test.py --concurrency 5` để tạo baseline.
3. Mở `http://127.0.0.1:8000/dashboard`. Dashboard runtime tích hợp FastAPI, đọc `data/logs.jsonl`, hiển thị 6 panel và tự refresh mỗi 30 giây.
4. Bộ lọc `All features` dùng ngưỡng dashboard chung; `Challenge feature` lọc theo feature/latency threshold trong file challenge local mà không trả nội dung challenge ra API. Để chụp incident, chọn `Challenge feature` và time range 15 phút.
5. Dùng bộ chọn time range để đổi giữa 15/30/60 phút; mặc định là 60 phút. Ngưỡng dashboard chung được nạp từ `config/dashboard.yaml`.
6. Langfuse vẫn là nơi mở trace/prompt version để điều tra sâu. Dashboard local dùng log đã scrub PII làm nguồn chuẩn.
7. Chạy validator:

```bash
python scripts/validate_dashboard.py
```

Validator kiểm tra cấu trúc contract; nó không thể chứng minh biểu đồ trong ảnh dùng đúng dữ liệu. Evidence runtime vẫn bắt buộc.

## SLO và alert

- Primary SLO: 99.5% request thành công trong ≤3000 ms theo cửa sổ 28 ngày.
- Error budget: `100% - 99.5% = 0.5%`; trong 10,000 request, tối đa 50 request được phép không đạt SLO.
- Ba alert symptom-based, owner, Slack channel và điều kiện nằm trong `config/alert_rules.yaml`; hướng dẫn xử lý nằm trong `docs/alerts.md`.

## Cách kiểm tra runtime

1. Lưu ảnh baseline và giá trị P95/error/cost hiện tại.
2. Bật một incident practice, ví dụ `python scripts/inject_incident.py --scenario <practice_scenario>`.
3. Chạy lại load test với cùng input và concurrency.
4. Xác nhận panel liên quan thay đổi theo đúng hướng theo loại practice scenario đã chọn.
5. Lọc log chậm, lấy correlation ID rồi mở trace có cùng ID.
6. Tắt incident bằng `python scripts/inject_incident.py --scenario <practice_scenario> --disable`.

## Evidence runtime

Chụp `http://127.0.0.1:8000/dashboard` sau khi chạy workload. Ảnh cần thấy đủ sáu panel có dữ liệu, time range, đơn vị và threshold. Nếu không đọc rõ ở một ảnh, chụp riêng nửa trên/dưới thành `11a` và `11b`.

Ảnh dashboard phải nhìn được tên panel, time range, đơn vị và threshold. Báo cáo phải dẫn lại trace ID hoặc log line dùng để giải thích thay đổi.
