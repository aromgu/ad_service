from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

TEXT_WEIGHTS = {
    "factuality": 0.30,
    "korean_naturalness": 0.20,
    "persuasiveness": 0.20,
    "tone_length": 0.15,
    "claim_safety": 0.10,
    "schema_compliance": 0.05,
}
IMAGE_WEIGHTS = {
    "product_preservation": 0.25,
    "prompt_adherence": 0.20,
    "visual_quality": 0.20,
    "ad_usability": 0.15,
    "speed": 0.10,
    "cost": 0.10,
}


def create_score_sheet(results_root: Path, output_csv: Path) -> int:
    rows: list[dict[str, object]] = []
    for result_path in sorted(results_root.glob("**/result.json")):
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        base = {
            "request_id": payload["request_id"],
            "reviewer": "",
            "unsupported_claim": "false",
            "notes": "",
        }
        rows.append(
            {
                **base,
                "kind": "copy",
                "asset_type": "copy",
                "model": payload["metrics"]["copy_model"],
                "latency_ms": payload["metrics"]["latency_ms"],
                "estimated_cost_usd": payload["metrics"]["estimated_cost_usd"],
            }
        )
        for asset in payload["assets"]:
            rows.append(
                {
                    **base,
                    "kind": "image",
                    "asset_type": asset["type"],
                    "model": asset["model"],
                    "latency_ms": asset["latency_ms"],
                    "estimated_cost_usd": asset["estimated_cost_usd"],
                }
            )
    fields = [
        "request_id",
        "reviewer",
        "kind",
        "asset_type",
        "model",
        *TEXT_WEIGHTS,
        *IMAGE_WEIGHTS,
        "unsupported_claim",
        "latency_ms",
        "estimated_cost_usd",
        "notes",
    ]
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _score(row: dict[str, str], weights: dict[str, float]) -> float:
    values = {name: float(row[name]) for name in weights}
    if any(value < 1 or value > 5 for value in values.values()):
        raise ValueError("all rubric scores must be between 1 and 5")
    return sum(values[name] * weight for name, weight in weights.items()) * 20


def aggregate_scores(scores_csv: Path, output_csv: Path) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    with scores_csv.open(encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            weights = TEXT_WEIGHTS if row["kind"] == "copy" else IMAGE_WEIGHTS
            if any(not row.get(name, "").strip() for name in weights):
                continue
            disqualified = row.get("unsupported_claim", "false").lower() == "true"
            if row["kind"] == "image" and float(row["product_preservation"]) < 4:
                disqualified = True
            groups[(row["kind"], row["model"])].append(
                {
                    "score": _score(row, weights),
                    "cost": float(row.get("estimated_cost_usd") or 0),
                    "latency": float(row.get("latency_ms") or 0),
                    "disqualified": disqualified,
                }
            )
    summaries: list[dict[str, Any]] = []
    for (kind, model), values in groups.items():
        summaries.append(
            {
                "kind": kind,
                "model": model,
                "mean_score": round(sum(item["score"] for item in values) / len(values), 2),
                "mean_cost_usd": round(sum(item["cost"] for item in values) / len(values), 6),
                "mean_latency_ms": round(
                    sum(item["latency"] for item in values) / len(values),
                    2,
                ),
                "samples": len(values),
                "eligible": not any(item["disqualified"] for item in values),
            }
        )
    summaries.sort(
        key=lambda item: (
            item["kind"],
            not item["eligible"],
            -item["mean_score"],
            item["mean_cost_usd"],
            item["mean_latency_ms"],
        )
    )
    fields = [
        "kind",
        "model",
        "mean_score",
        "mean_cost_usd",
        "mean_latency_ms",
        "samples",
        "eligible",
    ]
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summaries)
    return summaries
