#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

MODELS = {
    "qwen": "Qwen/Qwen3-8B",
    "flux": "black-forest-labs/FLUX.2-klein-4B",
    "birefnet": "ZhengPeng7/BiRefNet",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Download baseline model snapshots")
    parser.add_argument("models", nargs="+", choices=[*MODELS, "all"])
    parser.add_argument("--cache-dir", type=Path, default=Path("models/checkpoints"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    selected = list(MODELS) if "all" in args.models else args.models
    for key in selected:
        model_id = MODELS[key]
        print(f"{key}: {model_id}")
        if args.dry_run:
            continue
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise RuntimeError("install ML dependencies before downloading models") from exc
        snapshot_download(repo_id=model_id, cache_dir=args.cache_dir)


if __name__ == "__main__":
    main()
