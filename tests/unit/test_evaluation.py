import csv

from ad_service.evaluation import aggregate_scores


def test_evaluation_disqualifies_low_product_preservation(tmp_path) -> None:
    scores = tmp_path / "scores.csv"
    fields = [
        "request_id",
        "reviewer",
        "kind",
        "asset_type",
        "model",
        "product_preservation",
        "prompt_adherence",
        "visual_quality",
        "ad_usability",
        "speed",
        "cost",
        "unsupported_claim",
        "latency_ms",
        "estimated_cost_usd",
    ]
    with scores.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "request_id": "snack_001",
                "reviewer": "박창준",
                "kind": "image",
                "asset_type": "banner",
                "model": "candidate",
                "product_preservation": 3,
                "prompt_adherence": 5,
                "visual_quality": 5,
                "ad_usability": 5,
                "speed": 5,
                "cost": 5,
                "unsupported_claim": "false",
                "latency_ms": 100,
                "estimated_cost_usd": 0.01,
            }
        )
    summary = aggregate_scores(scores, tmp_path / "summary.csv")
    assert summary[0]["eligible"] is False
    assert summary[0]["mean_score"] == 90.0
