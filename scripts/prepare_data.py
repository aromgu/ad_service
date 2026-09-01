#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ad_service.data.dataset import prepare_aihub_eval_set  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare seven-product AI Hub evaluation set")
    parser.add_argument("--zip", required=True, type=Path, help="AI Hub sample ZIP")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data/processed/eval_v1",
    )
    args = parser.parse_args()
    manifest = prepare_aihub_eval_set(args.zip, args.output, PROJECT_ROOT)
    print(json.dumps({"products": len(manifest), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
