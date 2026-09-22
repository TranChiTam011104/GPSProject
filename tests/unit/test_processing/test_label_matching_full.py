"""Verify label matching per-user — sample 5 users có labels + 5 users không có."""
import sys
from pathlib import Path

sys.path.insert(0, ".")
from gps.data.processing import load_labels, load_plt_file, match_labels, clean_and_segment_trajectory

DATA_ROOT = Path("data/Geolife Trajectories 1.3/Data")

# ── 1. Phân loại user ────────────────────────────────────────────────────
users_with_labels = []
users_without_labels = []
for user_dir in sorted(DATA_ROOT.iterdir()):
    if not user_dir.is_dir():
        continue
    labels = load_labels(user_dir)
    if labels is not None and not labels.empty:
        users_with_labels.append((user_dir.name, len(labels), user_dir))
    else:
        users_without_labels.append(user_dir.name)

print(f"Users có labels.txt:    {len(users_with_labels)}")
print(f"Users không có:         {len(users_without_labels)}")

# ── 2. Lấy 5 user có labels, chạy pipeline đầy đủ, đếm mode ──────────────
print("\n=== 5 USER CÓ LABELS — Test match từng file .plt của user ===\n")
total_lbl_points = 0
total_unk_points = 0
for user_id, n_labels, user_dir in users_with_labels[:5]:
    labels = load_labels(user_dir)
    plt_files = sorted((user_dir / "Trajectory").glob("*.plt"))
    print(f"User {user_id}: {len(plt_files)} files, {n_labels} label entries")
    print(f"  Label range: {labels['start_datetime'].min()} → {labels['end_datetime'].max()}")
    print(f"  Label modes: {dict(labels['mode'].value_counts())}")

    user_labeled = 0
    user_unknown = 0
    files_with_match = 0
    for plt_file in plt_files:
        df = clean_and_segment_trajectory(plt_file, user_id, labels)
        if df is None:
            continue
        n_lbl = (df["mode"] != "unknown").sum()
        n_unk = (df["mode"] == "unknown").sum()
        user_labeled += n_lbl
        user_unknown += n_unk
        if n_lbl > 0:
            files_with_match += 1
    print(f"  → {files_with_match}/{len(plt_files)} files có match")
    print(f"  → Labeled: {user_labeled:,} | Unknown: {user_unknown:,}\n")
    total_lbl_points += user_labeled
    total_unk_points += user_unknown

print(f"Tổng 5 user: Labeled={total_lbl_points:,}, Unknown={total_unk_points:,}\n")

# ── 3. 5 user KHÔNG có labels → toàn bộ mode phải là 'unknown' ────────────
print("=== 5 USER KHÔNG CÓ LABELS — Toàn bộ phải là 'unknown' ===\n")
for user_id in users_without_labels[:5]:
    user_dir = DATA_ROOT / user_id
    plt_files = sorted((user_dir / "Trajectory").glob("*.plt"))
    total = 0
    for plt_file in plt_files:
        df = clean_and_segment_trajectory(plt_file, user_id, None)
        if df is None:
            continue
        total += len(df)
    print(f"  User {user_id}: {len(plt_files)} files, {total:,} điểm → toàn bộ mode='unknown' ✓")
