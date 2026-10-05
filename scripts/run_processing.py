"""Run the GPS cleaning pipeline from the command line.

Thin wrapper around `python -m gps.data.processing` that:

1. Resolves project root automatically (no need to ``cd`` first).
2. Picks sane defaults that match the GeoLife layout on disk.
3. Optionally limits to a single user (for smoke-testing).
4. Optionally wipes the output directory before re-running.

Usage examples
--------------

Full run (all 182 users, ~5-10 min on a 4-core laptop)::

    python scripts/run_processing.py

Smoke test on a single user::

    python scripts/run_processing.py --user 010 --verbose

Re-run with empty output dir (clean slate)::

    python scripts/run_processing.py --clean --workers 2

The script never deletes ``data/Geolife Trajectories 1.3/`` — only the
processed output directory.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ── Make `gps` package importable regardless of where the script is run ──────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

log = logging.getLogger("run_processing")


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python scripts/run_processing.py",
        description=(
            "Regenerate the cleaned GeoLife parquet dataset using the "
            "current `gps.data.processing` pipeline."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--data-dir", "-d",
        type=Path,
        default=PROJECT_ROOT / "data" / "Geolife Trajectories 1.3" / "Data",
        help="Thư mục chứa folder user (000/, 001/, ...)  [default: data/Geolife Trajectories 1.3/Data]",
    )
    p.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "users",
        help="Thư mục output cho partitioned parquet  [default: data/processed/users/]",
    )
    p.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Số CPU worker (parallel xử lý file .plt trong mỗi user) "
             "[default: min(4, os.cpu_count())]",
    )
    p.add_argument(
        "--gap-seconds",
        type=float,
        default=1200.0,
        help="Ngưỡng cắt segment (time gap), giây  [default: 1200 = 20 phút]",
    )
    p.add_argument(
        "--user",
        type=str,
        default=None,
        help="Smoke-test: chỉ chạy đúng một user (vd. '010'). "
             "Bỏ qua để chạy toàn bộ.",
    )
    p.add_argument(
        "--clean",
        action="store_true",
        help="Xóa sạch --output-dir trước khi chạy (KHÔNG xóa data thô).",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Bật DEBUG logging.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_argparser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Validate paths
    if not args.data_dir.exists():
        log.error("Data dir không tồn tại: %s", args.data_dir)
        return 1

    if args.user is not None:
        # Smoke-test mode: process_all_trajectories nhận trực tiếp thư mục của
        # 1 user (data_dir/{user}/Trajectory) - không cần dựng thư mục tạm.
        data_dir = args.data_dir / args.user
        if not (data_dir / "Trajectory").exists():
            log.error("User %s không tồn tại trong %s", args.user, args.data_dir)
            return 1
        log.info("Smoke test: chỉ chạy user %s", args.user)
    else:
        data_dir = args.data_dir

    output_dir = args.output_dir
    if args.clean and output_dir.exists():
        log.warning("Xóa output dir: %s", output_dir)
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build thresholds
    from gps.data.processing import (
        CleaningThresholds,
        process_all_trajectories,
    )
    thresholds = CleaningThresholds(max_gap_seconds=args.gap_seconds)

    log.info("Bắt đầu pipeline:")
    log.info("  data_dir   = %s", data_dir)
    log.info("  output_dir = %s", output_dir)
    log.info("  workers    = %s", args.workers or "min(4, cpu_count)")
    log.info("  gap        = %.0f s", args.gap_seconds)

    start = datetime.now()
    result = process_all_trajectories(
        data_dir=data_dir,
        output_dir=output_dir,
        n_workers=args.workers,
        thresholds=thresholds,
    )
    elapsed = (datetime.now() - start).total_seconds()

    if not result:
        log.error("Pipeline không tạo được output.")
        return 1

    log.info("=" * 60)
    log.info("TỔNG KẾT")
    log.info("  Tổng điểm:        %s", f"{result['total_rows']:,}")
    log.info("  Số user:          %d", result["n_users"])
    log.info("  Điểm quarantine:  %s", f"{result['n_quarantined']:,}")
    log.info("  Output dir:       %s", result["output_dir"])
    log.info("  Thời gian:        %.1f s (%.1f phút)", elapsed, elapsed / 60)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
