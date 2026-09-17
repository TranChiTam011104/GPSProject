## TRACK MLE — Home/Office/POI Inference (Track B1)

### Checkpoint 1 (Tuần 1-2): Stay-point detection → Home/Office classifier + API Spec

**Mục tiêu:** Có model location cơ bản chạy được, và API contract rõ ràng — ưu tiên tốc độ, không tối ưu accuracy.


| Tuần   | Task                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Tuần 1 | - Setup repo, môi trường, terraform - Load dataset Microsoft GeoLife, clean GPS trace (filter noise, speed-based filtering) - Xử lý timezone: convert timestamp trong file `.plt` (lưu theo GMT) sang local time (đa số dữ liệu thu thập tại Bắc Kinh, UTC+8) trước khi áp bất kỳ heuristic theo giờ nào - Stay-point detection: implement thuật toán phát hiện điểm dừng (time-threshold + distance-threshold) - Baseline heuristic: đêm = home, giờ hành chính = office                                                                                                            |
| Tuần 2 | - Định nghĩa API spec (OpenAPI/Swagger): endpoint `/classify/{user_id}`, input/output schema (lat/lng sequence → home/office/POI + confidence), error handling, versioning trong URL (`/v1/classify`) - Định nghĩa rõ cách tính `confidence` (vd: tỷ lệ thời gian ở tại location trong khung giờ kỳ vọng, hoặc mật độ điểm/số lần ghé của cluster từ DBSCAN) — vì bài toán không có nhãn nên confidence chỉ mang tính heuristic, không phải xác suất mô hình học có giám sát - Viết doc spec đầy đủ (request/response example, status code) - Review spec cùng mentor trước khi code |


**Tech dùng:** pandas, numpy, scikit-learn (DBSCAN), h3/geohash, FastAPI (để định nghĩa spec dễ tự sinh Swagger docs), OpenAPI.

**Deliverable checkpoint 1:**

- Stay-point detection + baseline heuristic chạy được (không cần tối ưu)
- File OpenAPI spec (`.yaml`) hoàn chỉnh, review được
- Repo có cấu trúc rõ ràng (model/, api/, tests/)
- Ghi chú đánh giá: GeoLife không có nhãn home/office chuẩn, nên đánh giá bằng cách lấy mẫu một số user, kiểm tra thủ công tính hợp lý (địa điểm home/office suy luận có khớp với pattern di chuyển không) thay vì đo accuracy tuyệt đối

---



### Checkpoint 2 (Tuần 3-4): Deploy Model + Versioning + Deploy Strategy

**Mục tiêu:** Model chạy như service thật trên AWS, có version control và hiểu 3 chiến lược deploy.


| Tuần   | Task                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tuần 3 | - Implement API theo spec đã định nghĩa bằng FastAPI - Đóng gói bằng Docker - Deploy lên AWS free tier: EC2 (t2.micro) hoặc Lambda + API Gateway (nếu model nhẹ) - Setup model versioning: MLflow Model Registry hoặc đơn giản là naming convention + S3 (model-v1, model-v2) - Model v1 = heuristic theo giờ áp trực tiếp trên từng stay-point riêng lẻ; v2 = dùng DBSCAN gộp các stay-point gần nhau thành 1 location trước khi áp heuristic (giảm nhiễu do GPS lệch vị trí giữa các lần ghé) |
| Tuần 4 | - Học và mô phỏng 3 chiến lược deploy: - **Shadow**: traffic gửi đến cả model cũ + mới, chỉ log kết quả model mới, không trả về user - **Canary**: route % nhỏ traffic (vd 10%) sang model mới - **Blue-green**: 2 environment riêng, switch traffic toàn bộ khi model mới pass test - Implement được ít nhất 1 trong 3 (khuyến nghị Canary vì dễ mô phỏng với API Gateway/ALB weighted routing hoặc đơn giản là random routing logic trong code)                                               |


**Tech dùng:** Docker, FastAPI, MLflow, AWS EC2/Lambda/API Gateway, GitLab CI/CD hoặc GitHub Actions cho CI/CD pipeline deploy.

**Deliverable checkpoint 2:**

- API đang chạy thật trên AWS, có thể gọi qua public/internal endpoint
- Có ít nhất 2 version model (heuristic vs clustering), quản lý qua registry
- Demo được 1 deploy strategy (canary/shadow/blue-green) hoạt động thực tế, kèm giải thích 3 chiến lược (điểm khác biệt, khi nào dùng)

---



### Checkpoint 3 (Tuần 5-6): Serving Strategy + Monitoring/Drift/Latency

**Mục tiêu:** Hiểu sync/async serving, và có hệ thống giám sát model trong production.


| Tuần   | Task                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tuần 5 | - So sánh Sync (request-response trực tiếp, dùng cho real-time classify) vs Async (queue-based, dùng SQS + worker, phù hợp batch classify cho tập user lớn) - Implement thử 1 flow async đơn giản: request → SQS → Lambda/worker xử lý → lưu kết quả → client poll hoặc callback - Đo latency của cả 2 approach                                                                                                                                                                 |
| Tuần 6 | - Setup monitoring: log request/response, latency (p50/p95/p99), error rate - Setup drift detection cơ bản (so sánh distribution location/trajectory theo thời gian — location drift); vì GeoLife là dữ liệu tĩnh (2007-2012), mô phỏng drift bằng cách replay trajectory theo thứ tự thời gian như traffic thật, không phải drift từ traffic sản xuất thực tế - Dashboard: CloudWatch (AWS free tier) hoặc Grafana + Prometheus nếu tự host - Tổng kết + demo toàn bộ hệ thống |


**Tech dùng:** AWS SQS, CloudWatch, Prometheus/Grafana (nếu muốn tự host, docker compose).

**Deliverable checkpoint 3 (cuối track):**

- So sánh sync vs async có số liệu latency thực tế
- Dashboard monitoring hiển thị latency + basic drift alert
- Demo end-to-end: từ request → model serving → log → monitor, kèm slide tổng kết toàn bộ 6 tuần (API spec → deploy → serving → monitoring)

---



### Bổ sung cho Track B1 (nằm trong các checkpoint trên)


| Component                       | Vị trí         | Deliverable thêm                                                                              |
| ------------------------------- | -------------- | --------------------------------------------------------------------------------------------- |
| Stay-point detection            | Checkpoint 1   | Thuật toán + threshold tuning                                                                 |
| Home/office heuristic vs DBSCAN | Checkpoint 1-2 | Benchmark 2 method                                                                            |
| POI categorization (bonus)      | Checkpoint 2   | Reverse geocode / h3 cell mapping                                                             |
| Privacy risk analysis           | Xuyên suốt     | Mục trong báo cáo (geohash làm thô, k-anonymity) — bám theo yêu cầu của doc de-bai-nghien-cuu |


**Lưu ý scope:**

- Microsoft GeoLife làm dataset chính (GPS trace dày, phù hợp stay-point detection).
- Gowalla/Brightkite chỉ dùng ở mức so sánh (chứng minh check-in data không suy luận được home/office), không làm end-to-end.
- Kèm mục phân tích rủi ro quyền riêng tư và kỹ thuật giảm nhạy cảm (geohash làm thô, k-anonymity).

