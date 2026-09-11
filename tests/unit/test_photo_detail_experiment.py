import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/photo_detail_experiment.py"


@pytest.fixture
def experiment():
    return runpy.run_path(str(SCRIPT))


@pytest.fixture
def plan():
    return {
        "product_title": "코디 사진",
        "hero_title": "브라운 컬러 코디",
        "hero_body": "사진 속 색상 조합을 확인하세요.",
        "story_title": "컬러와 디테일",
        "story_body": "사진에 담긴 외관을 소개합니다.",
        "features": [{"title": "관찰", "body": "색상", "evidence": "사진"}] * 3,
        "visible_items": ["상의", "하의"],
        "label_text_candidates": [],
        "missing_fields": ["소재", "사이즈", "원산지", "판매 구성"],
        "cautions": ["세트 판매 미확인"],
        "cta": "상품 정보 확인",
    }


def fake_client(plan, status="completed"):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            id="test-response",
            status=status,
            output_text=json.dumps(plan),
            usage=None,
            model_dump=lambda **_: {"status": status, "output_text": json.dumps(plan)},
        )

    return SimpleNamespace(responses=SimpleNamespace(create=create)), calls


def test_real_provider_contract_and_original_preservation(experiment, plan, tmp_path):
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (40, 60), "brown").save(source)
    client, calls = fake_client(plan)
    target = tmp_path / "result"
    experiment["generate"](source, target, "outfit", client)
    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-5.4-mini"
    assert calls[0]["store"] is False
    assert calls[0]["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg;")
    assert (target / "input.jpg").read_bytes() == source.read_bytes()
    result = json.loads((target / "result.json").read_text())
    assert result["status"] == "needs_review"
    assert result["image_generation_calls"] == 0
    assert result["estimated_cost_usd"] is None
    assert "세트 판매 미확인" in (target / "preview.html").read_text()
    with pytest.raises(FileExistsError):
        experiment["generate"](source, target, "outfit", client)
    assert len(calls) == 1


def test_html_escape_and_no_template_reinterpretation(experiment, plan, tmp_path):
    source = tmp_path / "photo.png"
    Image.new("RGB", (30, 30)).save(source)
    plan["hero_title"] = "<script>alert(1)</script>"
    plan["story_title"] = "{{IMAGE}}"
    client, _ = fake_client(plan)
    target = tmp_path / "result"
    experiment["generate"](source, target, "cosmetics", client)
    page = (target / "preview.html").read_text()
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "<h2>{{IMAGE}}</h2>" in page
    assert "성분·용량·효능은 별도 확인" in page
    with pytest.raises(ValueError):
        experiment["render"](target, "../escape.html")


@pytest.mark.parametrize("status,invalid", [("incomplete", False), ("completed", True)])
def test_incomplete_or_invalid_response_stops_without_retry(
    experiment, plan, tmp_path, status, invalid
):
    source = tmp_path / "photo.webp"
    Image.new("RGB", (40, 40)).save(source)
    if invalid:
        plan["features"] = []
    client, calls = fake_client(plan, status)
    target = tmp_path / "result"
    with pytest.raises((ValueError, ValidationError)):
        experiment["generate"](source, target, "cosmetics", client)
    assert len(calls) == 1
    assert (target / "response.json").exists()
    assert (target / "failure.json").exists()
    assert not (target / "preview.html").exists()


def test_source_and_category_rejected_before_call(experiment, plan, tmp_path):
    source = tmp_path / "photo.gif"
    Image.new("RGB", (40, 40)).save(source)
    client, calls = fake_client(plan)
    with pytest.raises(ValueError):
        experiment["generate"](source, tmp_path / "result", "outfit", client)
    with pytest.raises(ValueError):
        experiment["user_prompt"]("unknown")
    assert calls == []
    assert not (tmp_path / "result").exists()
