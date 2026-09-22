import os
import pandas as pd
import numpy as np

# 1. Đọc dữ liệu sạch đã xuất ra Parquet của User 010
parquet_path = r"../../../data/processed_v1/user_010.parquet"
labels_path = r"../../../data/Geolife Trajectories 1.3/Data/010/labels.txt"

assert os.path.exists(parquet_path), f"Chưa tìm thấy file {parquet_path}, hãy chờ pipeline chạy xong!"
df_clean = pd.read_parquet(parquet_path)

# 2. Đọc file labels.txt gốc
df_labels = pd.read_csv(
    labels_path, 
    sep=r'\s+', 
    skiprows=1, 
    header=None,
    names=['start_date', 'start_time', 'end_date', 'end_time', 'mode']
)
df_labels['start_datetime'] = pd.to_datetime(df_labels['start_date'] + ' ' + df_labels['start_time'], format='%Y/%m/%d %H:%M:%S')
df_labels['end_datetime'] = pd.to_datetime(df_labels['end_date'] + ' ' + df_labels['end_time'], format='%Y/%m/%d %H:%M:%S')
df_labels = df_labels[['start_datetime', 'end_datetime', 'mode']]

print("=== BẮT ĐẦU AUDIT DỮ LIỆU GÁN NHÃN ===")
print(f"Tổng số điểm GPS của User 010: {len(df_clean):,}")
print(f"Phân phối nhãn thực tế:\n{df_clean['mode'].value_counts()}\n")

# -------------------------------------------------------------------------
# TEST 1: KIỂM TRA TÍNH TOÀN VẸN (Không có điểm nào mang nhãn sai khoảng thời gian)
# -------------------------------------------------------------------------
labeled_points = df_clean[df_clean['mode'] != 'unknown']
print(f"-> Đang quét {len(labeled_points):,} điểm GPS có nhãn...")

is_valid_list = []
# Kiểm tra mẫu 10,000 điểm hoặc toàn bộ nếu máy đủ nhanh
sample_check = labeled_points.sample(min(10000, len(labeled_points)), random_state=42)

for _, pt in sample_check.iterrows():
    t = pt['datetime']
    m = pt['mode']
    # Tìm xem có khoảng nhãn nào chứa t và đúng mode không
    matched = df_labels[
        (df_labels['start_datetime'] <= t) & 
        (df_labels['end_datetime'] >= t) & 
        (df_labels['mode'] == m)
    ]
    is_valid_list.append(len(matched) > 0)

test1_passed = all(is_valid_list)
print(f"TEST 1 - Tính chuẩn xác của điểm có nhãn: {'✅ PASSED (100% Khớp)' if test1_passed else '❌ FAILED'}")

# -------------------------------------------------------------------------
# TEST 2: KIỂM TRA VÙNG TRỐNG (Không bị tràn nhãn sang thời gian không ghi chú)
# -------------------------------------------------------------------------
# Chọn một thời điểm mà người dùng chắc chắn KHÔNG ghi trong labels.txt (ví dụ: tháng 01/2008)
unknown_points = df_clean[df_clean['mode'] == 'unknown']
test2_passed = True

# Thử lấy ngẫu nhiên 1000 điểm 'unknown' kiểm tra xem có bị gán nhầm không
sample_unknown = unknown_points.sample(min(1000, len(unknown_points)), random_state=42)
for _, pt in sample_unknown.iterrows():
    t = pt['datetime']
    in_any_interval = df_labels[
        (df_labels['start_datetime'] <= t) & 
        (df_labels['end_datetime'] >= t)
    ]
    if len(in_any_interval) > 0:
        test2_passed = False
        break

print(f"TEST 2 - Tính cô lập của điểm unknown:    {'✅ PASSED (Không bị rò rỉ nhãn)' if test2_passed else '❌ FAILED'}")

# -------------------------------------------------------------------------
# TEST 3: SO SÁNH TRỰC QUAN 1 VÍ DỤ CỤ THỂ TRONG NGÀY 2008-04-01
# -------------------------------------------------------------------------
print("\n--- TRÍCH XUẤT THỰC TẾ 1 CUỐC TAXI NGÀY 2008-04-01 ---")
# Trong labels.txt: 2008/04/01 00:48:32 đến 2008/04/01 00:59:23 taxi
demo_trip = df_clean[
    (df_clean['datetime'] >= '2008-04-01 00:48:00') & 
    (df_clean['datetime'] <= '2008-04-01 01:02:00')
][['datetime', 'speed_kmh', 'mode']]

print(demo_trip.head(10).to_string(index=False))