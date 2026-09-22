#!/usr/bin/env python3
"""Generate ``configs/openapi.yaml`` from the FastAPI app.

Run this whenever routes or schemas change::

    python scripts/export_openapi.py [--out configs/openapi.yaml]

It also runs ``openapi-spec-validator`` if available and prints a summary.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# Ensure ``gps`` is importable when the script is run from any cwd.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Export FastAPI OpenAPI spec to YAML.")
    parser.add_argument(
        "--out",
        default=str(ROOT / "configs" / "openapi.yaml"),
        help="Output path (default: configs/openapi.yaml)",
    )
    args = parser.parse_args()

    from gps.api.main import app  # imported lazily so --help works without deps

    spec = app.openapi()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        yaml.safe_dump(spec, fp, sort_keys=False, allow_unicode=True)

    line_count = sum(1 for _ in open(out_path, encoding="utf-8"))
    paths = sorted(spec.get("paths", {}).keys())

    print(f"Saved: {out_path}")
    print(f"Size:  {line_count} lines")
    print(f"OpenAPI: {spec.get('openapi')}  Title: {spec.get('info', {}).get('title')}")
    print(f"Paths ({len(paths)}):")
    for p in paths:
        methods = list(spec["paths"][p].keys())
        print(f"  {','.join(m.upper() for m in methods):<12} {p}")

    # Optional validation — only if the dep is installed.
    try:
        from openapi_spec_validator import validate_spec  # type: ignore
        validate_spec(spec)
        print("\n✅ Spec is valid OpenAPI 3.")
    except ImportError:
        print("\n⚠️  openapi-spec-validator not installed; skipped validation.")
    except Exception as e:  # pragma: no cover - validation feedback
        print(f"\n❌ Spec is invalid: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
