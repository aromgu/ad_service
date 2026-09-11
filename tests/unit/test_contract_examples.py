"""협의용 예시 간 정합성 검사. 새 API의 스키마/실행 검증은 아닙니다."""

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "docs/contracts/draft-0.1"


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def fact_refs(value):
    if isinstance(value, dict):
        yield from value.get("fact_refs", [])
        for child in value.values():
            yield from fact_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from fact_refs(child)


def test_detail_example_references():
    request = read("detail_page.request.json")
    result = read("detail_page.response.json")
    assert request["schema_version"] == result["schema_version"] == "draft-0.1"
    assert result["request_id"] == request["request_id"]
    assert result["product_id"] == request["product"]["product_id"]
    assert result["product_revision"] == request["product"]["revision"]
    facts = {item["fact_id"] for item in request["product"]["facts"]}
    assert len(facts) == len(request["product"]["facts"])
    assert set(fact_refs(result)) <= facts
    assets = {item["asset_id"] for item in result["assets"]}
    assert len(assets) == len(result["assets"])
    assert request["content_request"]["primary_image_asset_id"] in assets
    assert len({section["section_id"] for section in result["sections"]}) == len(result["sections"])
    assert [s["type"] for s in result["sections"]] == request["content_request"]["section_plan"]
    for section in result["sections"]:
        if section["image"]:
            assert section["image"]["asset_id"] in assets
    for asset in result["assets"]:
        assert set(asset.get("layers", {}).values()) <= assets
    for image in request["product"]["images"]:
        assert image["width"] > 0 and image["height"] > 0
        if image["bbox"]:
            xmin, ymin, xmax, ymax = image["bbox"]
            assert 0 <= xmin < xmax <= image["width"]
            assert 0 <= ymin < ymax <= image["height"]
    assert result["execution"]["model_calls"] == 0
    assert result["execution"]["estimated_cost_usd"] is None


def test_text_revision_example_preserves_other_content():
    original = read("detail_page.response.json")
    request = read("section_revision.request.json")
    result = read("section_revision.response.json")
    assert request["schema_version"] == result["schema_version"] == original["schema_version"]
    assert request["request_id"] == result["request_id"]
    assert request["document_id"] == result["document_id"] == original["document_id"]
    assert request["base_revision"] == result["base_revision"] == original["revision"]
    assert result["revision"] == original["revision"] + 1
    change = result["change"]
    assert change["section_id"] == request["section_id"]
    assert change["target"] == request["target"] == "text"
    assert set(change) == {"section_id", "target", "content"}
    revised = deepcopy(original)
    targets = [s for s in revised["sections"] if s["section_id"] == change["section_id"]]
    assert len(targets) == 1
    targets[0]["content"] = change["content"]
    assert revised["assets"] == original["assets"]
    for before, after in zip(original["sections"], revised["sections"], strict=True):
        assert before["image"] == after["image"]
        assert before["layout"] == after["layout"]
        if before["section_id"] != change["section_id"]:
            assert before == after
        else:
            assert before["content"] != after["content"]
    facts = {f["fact_id"] for f in read("detail_page.request.json")["product"]["facts"]}
    assert set(fact_refs(change)) <= facts


def test_analysis_example_requires_confirmation_and_valid_evidence():
    request = read("product_analysis.request.json")
    result = read("product_analysis.response.json")
    assert request["schema_version"] == result["schema_version"] == "draft-0.1"
    assert request["request_id"] == result["request_id"]
    assert result["status"] == "needs_review"
    assets = {a["asset_id"]: a for a in request["reference_documents"]}
    candidates = {c["candidate_id"] for c in result["candidates"]}
    assert len(candidates) == len(result["candidates"])
    fields = set()
    for candidate in result["candidates"]:
        assert candidate["requires_confirmation"] is True
        assert candidate["field"] in request["requested_fields"]
        fields.add(candidate["field"])
        assert set(candidate.get("based_on_candidate_ids", [])) <= candidates
        if candidate["kind"] == "extracted_claim":
            assert candidate["evidence"]
        else:
            assert candidate["kind"] == "suggestion"
            assert candidate["reason"]
        for evidence in candidate["evidence"]:
            source = assets[evidence["asset_id"]]
            xmin, ymin, xmax, ymax = evidence["bbox"]
            assert 0 <= xmin < xmax <= source["width"]
            assert 0 <= ymin < ymax <= source["height"]
            assert evidence["text"]
    for unresolved in result["unresolved"]:
        assert unresolved["state"] == "unknown"
        assert unresolved["field"] not in fields
        fields.add(unresolved["field"])
    assert fields == set(request["requested_fields"])
    assert result["execution"]["model_calls"] == 0
    assert result["execution"]["estimated_cost_usd"] is None
