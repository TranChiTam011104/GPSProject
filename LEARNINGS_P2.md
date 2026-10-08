# LEARNINGS_P2 – Dự án 2/2: GeoLife Home / Office / POI

> Nguồn: `git log` (nhánh `cp1`, 17/09/2026 → 05/10/2026), 11 notebook trong `notebooks/` (mỗi notebook một quyết định, có output), `src/`, lần chạy pipeline ngày 05/10/2026.
> Cấu trúc: **Phần I** = kịch bản dựng slide HTML (4 slide, ~5 phút): bố cục, hình, số liệu, lời nói cho từng slide. **Phần II** = tài liệu chi tiết để tra cứu, không đưa lên slide.
> Quy ước hình: **[CÓ SẴN]** = file ảnh đã có trong repo, dùng nguyên; **[CHỤP]** = chụp màn hình từ file HTML / trang có sẵn; **[VẼ MỚI]** = vẽ khi dựng slide, số liệu lấy từ file CSV ghi kèm (không tự nghĩ số).

---

# PHẦN I – KỊCH BẢN SLIDE (≈5 phút)

## Slide 1 – Dự án và pipeline (~45 giây)
**Tiêu đề:** Suy ra nhà và cơ quan từ quỹ đạo GPS

**Bố cục:** một dòng mô tả bài toán ở trên, sơ đồ pipeline chiếm giữa slide, dòng trạng thái ở dưới.

**Hình 1.1 [VẼ MỚI] – Sơ đồ pipeline 4 khối, đọc từ trái sang phải**

| Khối | Số lớn trên khối | Dòng chú thích nhỏ |
|---|---|---|
| GPS thô | 24.88 M điểm | 182 user · 18,670 file `.plt` · giờ GMT |
| Làm sạch | 24.18 M điểm | 795 điểm đưa vào quarantine kèm lý do |
| Stay-point | 18,597 | ở yên ≥ 30 phút trong 200 m · 174 user |
| Classifier + API | v1 | API nhận stay-point · giờ địa phương |

- Ba khối đầu tô màu "đã xong, đã kiểm chứng"; khối cuối tô màu "đang làm".
- Nguồn số: `notebooks/README.md` (dòng 05, 10), log pipeline ngày 05/10.

**Nội dung chữ trên slide:**
- Bài toán: từ GPS thô của một người, tìm **Home**, **Office** và các địa điểm hay đến (POI), trả về qua API.
- Dữ liệu: Microsoft GeoLife, **không có nhãn nhà hay cơ quan**; nhãn chỉ là phương tiện di chuyển, phủ 20.1% số điểm.

**Lời nói:** "Dự án thứ hai suy ra nhà và cơ quan của một người từ dữ liệu GPS. Khó nhất là dữ liệu không có đáp án: không ai ghi nhãn đâu là nhà. Vì vậy phần lớn thời gian dành cho hai khối giữa: làm sạch và tìm stay-point, tức những lần ở yên một chỗ."

## Slide 2 – Mỗi ngưỡng đều được chứng minh bằng dữ liệu (~1.5 phút)
**Tiêu đề:** Mỗi ngưỡng đều được chứng minh bằng dữ liệu

**Bố cục:** trái 45% là hình 2.1 (ví dụ mở đầu); phải 55% là bảng 2.2. Dưới cùng một dòng nhỏ: "Mỗi quyết định = một notebook, có số liệu và giới hạn (11 notebook)".

**Hình 2.1 [CÓ SẴN] – Bộ lọc 180 km/h xoá dữ liệu thật**
- File: `notebooks/outputs/01_speed_threshold/figures/fig02_share_over_180kmh_by_mode.png`
- Hình cột: tỉ lệ điểm có nhãn bị bộ lọc 180 km/h xoá, theo phương tiện.
- Chú thích đè lên hình: **máy bay 56.7%** (5,205 / 9,186 điểm), **tàu hoả 3.6%** (19,968 / 560,962 điểm); các phương tiện khác ≈ 0.
- Số liệu: `notebooks/outputs/01_speed_threshold/tables/share_over_180kmh_by_mode.csv`.

**Bảng 2.2 – Năm quyết định chính** (giữ 3 cột, chữ to, cột "Kết quả" in đậm)

| Quyết định | Bằng chứng (dữ liệu thật) | Kết quả |
|---|---|---|
| Ngưỡng tốc độ bất khả thi | Điểm thật nhanh nhất 1,048 km/h, lỗi GPS chậm nhất 1,123 km/h | **1,100 km/h** |
| Cắt đoạn khi mất tín hiệu | Khoảng ngắt trong một chuyến: P99.9 = 252 s, P99.99 = 2,170 s | **20 phút** |
| Nối các file của một user | Tỉ lệ "ghi lại ở cùng chỗ" chạm mức nền 19.7% ở 18 h | **≤ 18 h**; số đêm tìm được 395 → 3,340 |
| Giờ địa phương | 2.61% số điểm ngoài UTC+8; UTC+8 cố định đặt 21.5% hoạt động vào 1–5 h sáng | **Theo toạ độ** |
| Bán kính / thời gian stay-point | 30 phút: 3.5 stay-point giả / 100 giờ đi xe (102 ở 5 phút); 200 m bao độ phân tán lúc đứng yên (136 m) | **200 m / 30 phút** |

**Hình dự phòng** (khi được hỏi "vì sao 18 h?" hoặc "vì sao 30 phút?"), để ở slide phụ, không trình chiếu nếu không ai hỏi:
- [CÓ SẴN] `notebooks/outputs/04_file_boundaries/figures/fig01_resume_rate_by_gap_hour.png`: đường tỉ lệ "file sau bắt đầu trong 200 m" giảm dần theo khoảng ngắt, chạm dải mức nền 19.7% ở **18 h** (đường đỏ).
- [CÓ SẴN] `notebooks/outputs/07_staypoint_thresholds/figures/fig02_threshold_sweep.png`: hình phải, stay-point giả rơi từ 102 (5 phút) xuống 3.5 (30 phút) trong khi khoảng dừng 30–45 phút vẫn bắt được ~53%; lên 45 phút thì tụt còn 33%.
- [CÓ SẴN] `notebooks/outputs/09_timezone_by_location/figures/fig01_active_hours_by_method.png`: đường đỏ (UTC+8 cố định) có đỉnh hoạt động lúc 1–2 h sáng, đường xanh (theo toạ độ) khớp đường xám tham chiếu.

**Lời nói:** "Ví dụ đầu tiên: một bộ lọc tốc độ 180 km/h có sẵn trong code mẫu. Nghe hợp lý, nhưng đo trên dữ liệu có nhãn thì nó xoá 57% điểm của người đi máy bay, tức là xoá dữ liệu thật. Từ đó, mọi ngưỡng đều phải có bằng chứng. Ví dụ ngưỡng tốc độ mới 1,100 km/h nằm đúng giữa điểm thật nhanh nhất và lỗi GPS chậm nhất."

## Slide 3 – Hộp công cụ khi không có đáp án đúng (~1.5 phút)
**Tiêu đề:** Hộp công cụ khi không có đáp án đúng

**Bố cục:** trái là danh sách 6 kỹ thuật (mỗi dòng: tên in đậm + một ví dụ ngắn); phải là 2 hình xếp dọc (3.1 trên, 3.2 dưới).

**Danh sách trên slide:**
1. **Khoảng trống giữa hai phân phối:** đặt ngưỡng giữa "điểm thật nhanh nhất" (1,048 km/h) và "lỗi chậm nhất" (1,123 km/h).
2. **Đối chứng âm và dương:** chuyến xe ≤ 3 h không thể có lần dừng 30 phút; khoảng trống giữa hai chuyến có nhãn là lúc đang ở đâu đó.
3. **Luôn có mức nền:** cặp user có file chung ở cạnh nhau ≥ nửa thời gian **39%**, so với **1.1%** ở các cặp khác.
4. **Ablation:** bật từng bước làm sạch và đo thay đổi (hình 3.1).
5. **Xem tận mắt ca cụ thể:** một stay-point 13.8 h biến mất vì khoảng cách 200.00 m → 200.54 m; nó chỉ có 2 phút điểm GPS thật.
6. **Kiểm chứng khi không có nhãn:** 9 tính chất trên 18,597 stay-point (0 vi phạm) và chấm mù 60 stay-point (hình 3.2).

**Hình 3.1 [VẼ MỚI] – Ablation: bước nào thật sự làm đổi stay-point?**
- Dạng: 4 cột (S0 → S3), trục chính là **stay-point dài nhất (giờ, thang log)**; ghi số lượng stay-point trên đầu mỗi cột.
- Số liệu (`notebooks/outputs/05_staypoint_cleaning_impact/tables/staypoints_by_stage.csv`):

| Giai đoạn | Mô tả ngắn trên trục | Stay-point | Dài nhất | Stay-point > 48 h |
|---|---|---|---|---|
| S0 | Thô, nối tất cả file | 19,443 | 35,024 h (**1,459 ngày**) | 282 |
| S1 | Thô, cắt tại khoảng ngắt > 18 h | 18,598 | 43.8 h | 0 |
| S2 | + xử lý trùng | 18,597 | 43.8 h | 0 |
| S3 | + loại điểm gai | 18,597 | 43.8 h | 0 |

- Chú thích dưới hình: "Xử lý trùng đổi 0.8% stay-point; loại điểm gai đổi 0. Bước quyết định là cách nối file."
- Hình phụ tuỳ chọn [CHỤP]: `notebooks/outputs/05_staypoint_cleaning_impact/maps/staypoint_stages_user055.html`, bật lớp S0, khoanh vòng stay-point 4 năm ghép từ ~7 phút dữ liệu.

**Hình 3.2 [VẼ MỚI] – Chấm mù 60 stay-point**
- Dạng: thanh ngang xếp chồng (đúng / sai / không chắc) cho từng nhóm, cạnh mỗi thanh ghi độ chính xác và khoảng tin cậy 95%.
- Số liệu (`notebooks/outputs/10_staypoint_validation/tables/audit_result.csv`):

| Nhóm (nhãn trên trục) | Đúng | Sai | Không chắc | Độ chính xác (95% CI) |
|---|---|---|---|---|
| Ngẫu nhiên (đại diện toàn bộ) | 23 | 2 | 5 | **92%** (75–98%) |
| Ngắn 30–40 phút | 4 | 1 | 1 | 80% |
| Dài > 12 h | 6 | 0 | 0 | 100% |
| Ít điểm GPS (< 10% thời gian) | 6 | 0 | 0 | 100% |
| Qua đêm | 5 | 0 | 1 | 100% |
| "Giả" theo nhãn chuyến đi | 3 | 3 | 0 | 50% |

- Chú thích dưới hình: "90.6% thời gian ở lại nằm trong stay-point đúng. Lỗi duy nhất: đi chậm trên đường 30–45 phút."
- Hình phụ tuỳ chọn [CHỤP]: trang chấm https://claude.ai/artifact/2ncyaQ5UxAppi4fvmTN9i3, một stay-point đúng (vd. `s05`, khuôn viên Thanh Hoa) và một stay-point sai (vd. `s22`, đường lớn) đặt cạnh nhau: biểu đồ khoảng cách tới tâm, ca đúng nằm phẳng dưới đường 200 m, ca sai trải dọc một đường.

**Lời nói:** "Không có đáp án thì kiểm chứng thế nào? Đây là sáu kỹ thuật dùng nhiều nhất. Hai ví dụ: tắt bật từng bước làm sạch cho thấy bước quyết định là cách nối các file, không phải các bước xử lý lỗi; nối sai thì ra một stay-point dài bốn năm. Và để biết stay-point có đúng không, chúng tôi chấm mù một mẫu ngẫu nhiên: đúng 92%, lỗi duy nhất là xe đi chậm trên đường lớn."

## Slide 4 – Bài học (~1 phút)
**Tiêu đề:** 4 điều rút ra

**Bố cục:** 4 ô (2 × 2), mỗi ô: câu bài học in đậm + một con số lớn + một dòng giải thích. Ô 1 to hơn hoặc có hình 4.1 bên cạnh.

| Ô | Câu bài học | Con số lớn | Dòng giải thích |
|---|---|---|---|
| 1 | Code đúng chưa chắc kết quả đúng | **152 / 174** user | Classifier áp khung giờ "nhà ban đêm" lên giờ GMT: chạy không lỗi, test vẫn pass, nhưng Home sai |
| 2 | "Không làm gì" cũng cần bằng chứng | **0.03%** · **14 m** | Nhảy vị trí chạm 0.03% thời gian ở lại; cắt đuôi cửa sổ chỉ dịch tâm 14 m, nên giữ nguyên |
| 3 | Bằng chứng chỉ lấy từ dữ liệu thật | **1.2–2.3%** | Không nội suy; ngưỡng riêng theo phương tiện bị bác vì loại nhầm 1.2–2.3% điểm thật |
| 4 | Hiểu dữ liệu trước khi mô hình hoá | **20.1%** · **821 file** | Nhãn chỉ phủ 20.1% điểm; 821 file giống hệt nhau ở 52 user → phải gộp khi đánh giá |

**Hình 4.1 [VẼ MỚI] – Lỗi giờ GMT trong một hình**
- Dạng: hai thanh thời gian ngang cùng một ngày (thứ Tư 22/10/2008), trục 0–24 h.
  - Thanh trên "Giờ Bắc Kinh": stay-point ở nhà **22:30 → 06:30**, nằm trong vùng tô "khung Home 22–06".
  - Thanh dưới "Giờ GMT (code cũ đọc)": cùng stay-point thành **14:30 → 22:30**, giờ đến 14:30 rơi vào vùng tô "khung Office 9–18" → bị gán **Office**.
- Ví dụ lấy đúng từ test `tests/unit/test_models/test_heuristic.py::TestLocalTime::test_beijing_night_is_home_not_office`.

**Lời nói:** "Bài học tôi thấy rõ nhất: code đúng chưa chắc kết quả đúng. Classifier đọc giờ GMT nên người ở nhà lúc 10 giờ tối Bắc Kinh bị coi là đang ở cơ quan lúc 2 giờ chiều. Code chạy, test pass, nhưng sửa xong thì Home đổi ở 152 trên 174 user. Test kiểm code làm đúng thiết kế; phân tích dữ liệu kiểm thiết kế có đúng với thực tế."

**Kết thúc (một dòng cuối slide 4):** Tiếp theo: tính Home/Office theo **thời gian ở lại trong khung giờ** (quy tắc theo giờ đến chỉ tìm được Home cho 130/174 user), v2 gom địa điểm bằng DBSCAN.

## Danh sách hình cần chuẩn bị

| Hình | Loại | Nguồn |
|---|---|---|
| 1.1 Pipeline 4 khối | VẼ MỚI | số trong bảng slide 1 |
| 2.1 Bộ lọc 180 km/h | CÓ SẴN | `notebooks/outputs/01_speed_threshold/figures/fig02_share_over_180kmh_by_mode.png` |
| 2.x Dự phòng: 18 h, 30 phút, múi giờ | CÓ SẴN | `04_file_boundaries/figures/fig01_resume_rate_by_gap_hour.png`, `07_staypoint_thresholds/figures/fig02_threshold_sweep.png`, `09_timezone_by_location/figures/fig01_active_hours_by_method.png` |
| 3.1 Ablation S0–S3 | VẼ MỚI | `05_staypoint_cleaning_impact/tables/staypoints_by_stage.csv` |
| 3.1 phụ: stay-point 4 năm | CHỤP | `05_staypoint_cleaning_impact/maps/staypoint_stages_user055.html` |
| 3.2 Chấm mù | VẼ MỚI | `10_staypoint_validation/tables/audit_result.csv` |
| 3.2 phụ: ca đúng / ca sai | CHỤP | trang chấm, stay-point `s05` và `s22` |
| 4.1 Lỗi giờ GMT | VẼ MỚI | ví dụ trong test `TestLocalTime` |

(Các đường dẫn ở bảng trên tính từ `notebooks/outputs/`, trừ dòng 2.1.)

---

# PHẦN II – TÀI LIỆU CHI TIẾT (tra cứu, không đưa lên slide)

## A. Bảng quyết định đầy đủ

| Notebook | Câu hỏi | Bằng chứng chính | Quyết định trong `src/` |
|---|---|---|---|
| 01 `speed_threshold` | Ngưỡng tốc độ nào là bất khả thi? | Thật nhanh nhất 1,048.1 km/h, lỗi chậm nhất 1,122.7 km/h; nhiễu GPS ≈ 34 m (P99.9 bước 1 s); ngưỡng theo phương tiện loại nhầm 1.2–2.3% | `impossible_speed_kmh = 1100` |
| 02 `duplicate_timestamps` | Cùng một giây có nhiều toạ độ thì giữ cái nào? | 99.96% nhóm có ứng viên cách nhau trung vị 1.4 m (P99 14 m); chọn theo tốc độ tới điểm neo dịch trung vị 0.7 m; nhóm mơ hồ > 200 m: hai quy tắc chọn bất đồng 27/52 | Chọn ứng viên có `max(v_in, v_out)` nhỏ nhất; quarantine nhóm mơ hồ / không hợp lệ |
| 03 `segment_gap_threshold` | Khoảng ngắt bao lâu thì cắt đoạn? | Trong chuyến: P99.9 252 s, P99.99 2,170 s; 55.4% ranh giới chuyến có nhãn có khoảng ngắt ≤ 5 s | `max_gap_seconds = 1200`; segment không dùng để tìm chuyến |
| 04 `file_boundaries` | Chạy stay-point theo từng file, nối tất cả, hay nối có điều kiện? | Mức nền 19.7% ± 1.5% đạt ở 18 h; đêm 395 → 3,340; user không có đêm 96 → 41; đêm khôi phục trùng chỗ ngủ 49.5% so với 18.7–24.3% | Cắt tại khoảng ngắt > 18 h (`MAX_GAP_HOURS`) |
| 05 `staypoint_cleaning_impact` | Mỗi bước làm sạch đổi stay-point bao nhiêu? | Nối file: 19,443 → 18,598, dài nhất 1,459 ngày → 43.8 h; trùng: 0.8%; điểm gai: 0 | Không đổi (kiểm chứng) |
| 06 `gaps_inside_staypoints` | Có cắt stay-point tại khoảng không có điểm bên trong? | Chuyến có nhãn nằm trọn trong khoảng đó chỉ 0.2–1.9%; cắt ở 1–3 h mất 27–55% thời gian ở lại | Không cắt; lưu thêm `observed_minutes` |
| 07 `staypoint_thresholds` | 200 m / 30 phút có đúng? Có cắt đuôi cửa sổ? | 30 phút: 3.5 giả / 100 giờ đi xe; 200 m ≥ độ phân tán 136 m; cắt đuôi: tâm dịch 14 m, giờ lệch < 0.3 phút | Giữ 200 m / 30 phút, CENTROID, không cắt đuôi |
| 08 `trajectory_jumps` | Các cú nhảy vị trí nhiều điểm có cần quy tắc? | 58 khối lệch chạm 11 stay-point (0.03% thời gian); 250 lệch một phía trung vị 1.8 km trong 4 s | Không thêm quy tắc |
| 09 `timezone_by_location` | UTC+8 cố định có đúng cho mọi user? | 2.61% điểm (16 user) ở múi giờ khác; giờ 1–5 h sáng 21.5% (UTC+8) so với 7.4% (theo vị trí), mốc 5.7% | Múi giờ IANA theo toạ độ |
| 10 `staypoint_validation` | Stay-point có đúng không? | 9 tính chất, 0 vi phạm / 18,597; chấm mù 60: 92% (75–98%), 90.6% thời gian đúng | Giữ detector; thêm integration test |
| 11 `shared_recordings` | File giống hệt nhau giữa các user là gì? | 821 file, 52 user, 12% số điểm; quen với chính chủ 75.5% so với 23.4%; ở cạnh nhau 39% so với 1.1% | Không đổi (mỗi user độc lập); gộp khi đánh giá |

## B. Kỹ thuật phân tích dữ liệu, cách làm cụ thể

| Kỹ thuật | Cách làm | Ví dụ trong dự án |
|---|---|---|
| Khoảng trống giữa hai phân phối | Tách nhóm "chắc chắn thật" và "chắc chắn lỗi", đặt ngưỡng ở giữa | 1,048 km/h (máy bay thật) và 1,123 km/h (lỗi) → 1,100 |
| Mức nền | So mỗi con số với cùng phép đo trên dữ liệu ngẫu nhiên / không liên quan | Mức nền 19.7% của khoảng ngắt > 24 h; người lạ 23.4%; cặp không có file chung 1.1% |
| Đối chứng âm / dương | Chọn tình huống chắc chắn không / chắc chắn có hiện tượng | Chuyến xe ≤ 3 h (âm); khoảng giữa hai chuyến có nhãn (dương). Nhãn "walk" dài bị loại vì nhiễu |
| Quét ngưỡng | Chạy lại với nhiều giá trị, xem đường cong, tìm điểm gãy | Bán kính 50–500 m, thời gian 5–60 phút; 200 m "hợp lý" nhưng không có điểm tối ưu |
| Ablation | Bật lần lượt từng bước, đo khác biệt | 4 giai đoạn S0–S3 trên 182 user |
| Xem ca cụ thể | Lấy ví dụ cực đoan và lần ngược tới điểm GPS | User 055: stay-point 4 năm từ ~7 phút dữ liệu; user 065: 200.00 m và 200.54 m |
| Kiểm tra tính chất + đột biến | Viết điều luôn phải đúng, rồi cố tình làm hỏng để chắc phép kiểm bắt được | 9 tính chất; các lỗi cố ý bị bắt 100% |
| Mẫu ngẫu nhiên phân tầng, chấm mù | 30 ca ngẫu nhiên đều + 6 ca mỗi nhóm rủi ro; người chấm không biết nhóm; khoảng tin cậy Wilson | 92% (75–98%); lỗi duy nhất: đi chậm trên đường 30–45 phút |
| Chỉ dữ liệu thật | Mọi kiểm chứng trên cặp / bộ ba điểm GPS thật, không nội suy | Đo nhiễu GPS bằng bước 1 giây của người đi bộ |

## C. Bẫy đã gặp

| Bẫy | Biểu hiện | Cách nhận ra / sửa |
|---|---|---|
| Ngưỡng thừa hưởng | 180 km/h xoá 57% điểm máy bay | Đo trên dữ liệu có nhãn; bỏ bộ lọc |
| Ngưỡng theo phân vị dữ liệu | Phân vị của nhãn "walk" ra 108.8 km/h, vô lý về vật lý | Loại nhiễu GPS trước, so với tốc độ thực tế từ nguồn ngoài |
| Nhãn không phải đáp án | Nhãn "walk" dài cả ngày chứa cả lúc dừng thật, làm phồng số stay-point "giả" | Đổi đối chứng âm sang chuyến xe ≤ 3 h; chấm mù cho thấy chỉ một nửa số "giả" là sai |
| Giờ GMT | Ở nhà 22:30 Bắc Kinh bị coi là ở cơ quan lúc 14:30 | Đổi giờ theo vị trí; Home đổi ở 152/174 user |
| Kết quả không tất định | Thứ tự dòng output đổi theo tiến trình chạy xong trước, làm một bảng đổi giữa hai lần chạy | Sắp xếp theo (file, thời gian) trước khi ghi; thêm test |
| NaN lan truyền | Điểm đầu thiếu độ cao làm độ cao trung bình của cả stay-point thành NaN | Lấy trung bình các giá trị hợp lệ; NaN chỉ khi không có giá trị nào |
| Notebook không lưu output | Chạy ngầm nên người đọc không thấy kết quả | `scripts/run_notebooks.py` chạy bằng kernel thật, lưu output; chỉ chạy lại khi code hoặc dữ liệu đổi |
| Bằng chứng ngoài notebook | Số liệu trong kết luận lấy từ script tạm | Mọi con số trong kết luận phải được chính notebook in ra |

## D. Tiến độ theo ngày

- **17/09:** dựng repo.
- **22/09:** khung checkpoint 1 (stay-point, heuristic v1, spec FastAPI).
- **28/09:** rà soát toàn bộ, lập lộ trình: bằng chứng làm sạch → stay-point → classifier.
- **29/09:** tái cấu trúc notebook theo chuỗi bằng chứng (01–03, 06); notebook 04 (nối file) và 09 (múi giờ); bỏ pipeline "full" không có bằng chứng.
- **01/10:** họp mentor; xử lý trùng chọn theo tốc độ; kiểm tra lại nhóm có điểm neo là điểm gai; notebook 07 (ngưỡng stay-point), 08 (nhảy vị trí).
- **05/10:** notebook 05 (tác động làm sạch), 10 (kiểm chứng stay-point, chấm mù), 11 (file chung); stay-point thành đầu ra pipeline; API chỉ nhận stay-point; classifier dùng giờ địa phương. 123 test.

## E. Công cụ và kỹ thuật lập trình mới dùng

| Nhóm | Đã dùng |
|---|---|
| Xử lý dữ liệu lớn | pandas vector hoá, haversine vector hoá, xử lý tuần tự theo user + `ProcessPoolExecutor` để không tràn RAM, Parquet |
| Không gian / thời gian | `sklearn.neighbors.BallTree` (haversine), `timezonefinder` + `zoneinfo` (múi giờ IANA, giờ mùa hè), ghép theo phút để tìm người ở cạnh nhau |
| Thống kê | Phân vị, khoảng tin cậy Wilson, mẫu phân tầng có seed cố định |
| Trực quan | matplotlib, bản đồ folium nhiều lớp, trang chấm trên claude.ai (canvas, lưu kết quả vào cơ sở dữ liệu của trang) |
| Tái lập | Cache theo user, seed cố định, output sắp xếp cố định, `nbclient` lưu output notebook |

## F. Trạng thái và việc tiếp theo

- **Xong:** pipeline làm sạch (24,177,459 điểm, 795 điểm quarantine kèm lý do); stay-point là đầu ra chính thức (`data/processed/staypoints/`); kiểm chứng tầng 1–4; API nhận stay-point; classifier dùng giờ địa phương.
- **Tiếp theo:**
  - tính theo thời gian ở lại trong khung giờ (quy tắc theo giờ đến chỉ tìm được Home cho 130/174 user);
  - kết quả "chưa đủ dữ liệu";
  - cấu hình từ settings;
  - v2 gom địa điểm bằng DBSCAN;
  - đánh giá classifier, gộp các user có file chung.
