# LEARNINGS_P2 – Dự án 2/2: GeoLife Home / Office / POI

> Nguồn: `git log` (nhánh `cp1`, 17/09/2026 → 05/10/2026), 11 notebook trong `notebooks/` (mỗi notebook một quyết định, có output), `src/`, lần chạy pipeline ngày 05/10/2026.
> Cấu trúc: **Phần I** = nội dung dùng cho slide (4 slide, ~5 phút). **Phần II** = tài liệu chi tiết để tra cứu, không đưa lên slide.

---

# PHẦN I – NỘI DUNG SLIDE (≈5 phút)

## Slide 1 – Dự án và pipeline (~45 giây)
**Tiêu đề:** Suy ra nhà và cơ quan từ quỹ đạo GPS

- Bài toán: từ GPS thô của một người, tìm **Home**, **Office** và các địa điểm hay đến (POI), trả về qua API.
- Dữ liệu: Microsoft GeoLife, 182 user, 18,670 file `.plt`, 24.9 triệu điểm, giờ GMT, **không có nhãn nhà hay cơ quan**.
- Hình (sơ đồ ngang):
  `GPS thô (24.88 M điểm)` → `Làm sạch (24.18 M)` → `Stay-point (18,597)` → `Classifier v1 + API`
- Trạng thái: làm sạch và stay-point đã xong và đã kiểm chứng; API nhận stay-point; classifier đang được sửa.

## Slide 2 – Điều học được nhiều nhất: tìm bằng chứng cho từng quyết định (~1.5 phút)
**Tiêu đề:** Từ "dùng lại xử lý có sẵn" sang "chứng minh bằng dữ liệu"

- Xuất phát điểm: là lập trình viên, quen dùng lại các bước xử lý và ngưỡng có sẵn trong bài báo hoặc code mẫu.
- Ví dụ mở đầu: bộ lọc tốc độ **180 km/h** có sẵn trong prototype trông hợp lý. Đo trên dữ liệu có nhãn thì nó **xoá 57% số điểm đi máy bay và 3.6% số điểm đi tàu**, tức là dữ liệu thật bị xoá. Đã bỏ.
- Cách làm mới: mỗi quyết định có một notebook, trả lời một câu hỏi, có số liệu và giới hạn.

| Quyết định | Bằng chứng (dữ liệu thật) | Kết quả |
|---|---|---|
| Ngưỡng tốc độ bất khả thi | Điểm thật nhanh nhất 1,048 km/h, lỗi GPS chậm nhất 1,123 km/h | **1,100 km/h** |
| Cắt đoạn khi mất tín hiệu | Khoảng ngắt trong một chuyến: P99.9 = 252 s, P99.99 = 2,170 s | **20 phút** |
| Nối các file của một user | Tỉ lệ "ghi lại ở cùng chỗ" chạm mức nền (19.7%) ở 18 h | **≤ 18 h**; số đêm tìm được 395 → 3,340 |
| Giờ địa phương | 2.61% số điểm ở ngoài UTC+8; UTC+8 cố định đặt 21.5% hoạt động vào 1–5 h sáng | **Theo toạ độ** |
| Bán kính / thời gian stay-point | 30 phút: 3.5 stay-point giả / 100 giờ đi xe (102 ở 5 phút); 200 m bao độ phân tán lúc đứng yên (136 m) | **200 m / 30 phút** |

## Slide 3 – Các kỹ thuật phân tích dữ liệu đã học (~1.5 phút)
**Tiêu đề:** Hộp công cụ khi không có đáp án đúng

1. **Tìm khoảng trống giữa hai phân phối**: đặt ngưỡng giữa "điểm thật nhanh nhất" và "lỗi chậm nhất", không lấy một phân vị tuỳ ý.
2. **Đối chứng âm và dương**: chuyến đi bằng xe ≤ 3 h không thể có lần dừng 30 phút (âm); khoảng trống giữa hai chuyến đi có nhãn là lúc đang ở đâu đó (dương).
3. **Luôn có mức nền**: một con số chỉ có nghĩa khi so với ngẫu nhiên. Ví dụ: các cặp user có file chung ở cạnh nhau ≥ một nửa thời gian 39%, so với **1.1%** ở các cặp khác.
4. **Ablation**: bật từng bước làm sạch và đo thay đổi. Bước quyết định là **cách nối file**: nối tất cả tạo ra một stay-point dài **1,459 ngày** từ vài phút dữ liệu. Xử lý trùng chỉ đổi 0.8% stay-point; loại điểm gai đổi 0.
5. **Xem tận mắt ca cụ thể**: một stay-point 13.8 h biến mất chỉ vì khoảng cách đổi từ 200.00 m thành 200.54 m, và stay-point đó chỉ có 2 phút điểm GPS thật.
6. **Kiểm chứng khi không có nhãn**: kiểm 9 tính chất bắt buộc trên cả 18,597 stay-point (0 vi phạm), cố ý làm hỏng dữ liệu để chắc bộ kiểm tra bắt được lỗi, rồi **chấm mù 60 stay-point** rút ngẫu nhiên: độ chính xác **92%** (khoảng tin cậy 75–98%).
- Gợi ý hình: biểu đồ khoảng cách tới tâm theo thời gian trên trang chấm (stay-point đúng nằm phẳng dưới đường 200 m).

## Slide 4 – Bài học (~1 phút)
**Tiêu đề:** 4 điều rút ra

1. **Code đúng chưa chắc kết quả đúng.** Test kiểm code làm đúng như thiết kế; phân tích dữ liệu kiểm thiết kế có khớp thực tế không. Classifier áp khung giờ "nhà ban đêm" lên giờ GMT, chạy không lỗi, test vẫn pass, nhưng làm sai Home của **152/174 user**.
2. **"Không làm gì" cũng cần bằng chứng.** Nhảy vị trí nhiều điểm (chạm 0.03% thời gian ở lại) và cắt đuôi cửa sổ stay-point (tâm chỉ dịch 14 m) đều được đo rồi mới quyết định giữ nguyên.
3. **Bằng chứng chỉ lấy từ dữ liệu thật.** Không nội suy, không tạo vị trí giả. Ý tưởng ngưỡng riêng cho từng phương tiện bị bác vì loại nhầm 1.2–2.3% điểm thật.
4. **Hiểu dữ liệu trước khi mô hình hoá.** Nhãn chỉ phủ 20.1% số điểm và chỉ là phương tiện di chuyển; 821 file giống hệt nhau nằm ở 52 user. Hiểu những điều này quyết định cách đánh giá mô hình về sau.

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
