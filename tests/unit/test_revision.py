import hashlib
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ad_service.api.main import create_app
from ad_service.api.schemas.revision import EditableDocument, RevisionProposal
from ad_service.pipelines.revision import (
    RevisionConflict,
    document_hash,
    preview_revision,
    render_revision_preview,
)


@pytest.fixture
def document():
    return EditableDocument.model_validate(
        {
            "document_id": "outfit",
            "revision": 3,
            "assets": [
                {"asset_id": a, "role": "additional_product", "width": 700, "height": 1040}
                for a in ("original", "replacement")
            ],
            "facts": [
                {
                    "fact_id": "size",
                    "label": "사이즈",
                    "value": "M",
                    "source": {"type": "seller_input", "reference": "판매자 입력"},
                }
            ],
            "missing_fields": ["소재"],
            "sections": [
                {
                    "section_id": "hero",
                    "kind": "hero",
                    "blocks": [
                        {
                            "content": {
                                "block_id": "title",
                                "type": "text",
                                "role": "heading",
                                "text": "사용자가 직접 고친 제목",
                            }
                        },
                        {
                            "content": {
                                "block_id": "photo",
                                "type": "image",
                                "source_asset_id": "original",
                                "alt": "원본 사진",
                            }
                        },
                    ],
                },
                {
                    "section_id": "story",
                    "kind": "story",
                    "blocks": [
                        {
                            "content": {
                                "block_id": "body",
                                "type": "text",
                                "role": "body",
                                "text": "직접 수정한 설명은 보존",
                            }
                        },
                    ],
                },
                {
                    "section_id": "specs",
                    "kind": "specifications",
                    "blocks": [
                        {
                            "content": {
                                "block_id": "table",
                                "type": "table",
                                "rows": [{"label": "사이즈", "value": "M", "fact_refs": ["size"]}],
                            }
                        },
                    ],
                },
            ],
        }
    )


def proposal(document, operations):
    return RevisionProposal.model_validate(
        {
            "request_id": "revision-test",
            "base_revision": document.revision,
            "base_sha256": document_hash(document),
            "instruction": "선택한 부분을 수정해줘",
            "decision": "ready",
            "operations": operations,
        }
    )


def test_targeted_text_and_style_preserve_user_edits(document):
    before = document.model_dump()
    result = preview_revision(
        document,
        proposal(
            document,
            [
                {"op": "replace_text", "block_id": "title", "text": "브라운 코디"},
                {"op": "set_style", "block_id": "title", "color": "#884422"},
            ],
        ),
    )
    assert document.model_dump() == before
    assert result.document.sections[1:] == document.sections[1:]
    assert result.document.sections[0].blocks[1] == document.sections[0].blocks[1]
    assert result.document.assets == document.assets
    assert result.document.facts == document.facts
    assert result.document.revision == 4
    assert result.document.sections[0].blocks[0].style.font_size == 24
    assert result.model_calls == 0 and not result.persisted


def test_all_structural_operations(document):
    operations = [
        {
            "op": "add_section",
            "index": 1,
            "section": {
                "section_id": "cta",
                "kind": "cta",
                "blocks": [
                    {
                        "content": {
                            "block_id": "cta_text",
                            "type": "text",
                            "role": "cta",
                            "text": "정보 확인",
                        }
                    }
                ],
            },
        },
        {
            "op": "add_block",
            "section_id": "story",
            "index": 1,
            "block": {
                "content": {
                    "block_id": "extra",
                    "type": "text",
                    "role": "body",
                    "text": "추가 설명",
                }
            },
        },
        {"op": "move_block", "block_id": "extra", "section_id": "hero", "index": 0},
        {"op": "remove_block", "block_id": "extra"},
        {"op": "set_layout", "section_id": "hero", "layout": "image_right"},
        {"op": "move_section", "section_id": "cta", "index": 3},
        {"op": "remove_section", "section_id": "story"},
        {"op": "replace_image", "block_id": "photo", "asset_id": "replacement", "alt": "교체"},
        {
            "op": "replace_table",
            "block_id": "table",
            "rows": [{"label": "사이즈", "value": "M", "fact_refs": ["size"]}],
        },
    ]
    result = preview_revision(document, proposal(document, operations))
    assert [s.section_id for s in result.document.sections] == ["hero", "specs", "cta"]
    assert result.document.sections[0].layout == "image_right"
    assert result.document.sections[0].blocks[1].content.source_asset_id == "replacement"


def test_image_edit_is_only_unstarted_intent(document):
    result = preview_revision(
        document,
        proposal(
            document,
            [
                {"op": "edit_image", "block_id": "photo", "instruction": "배경만 밝게"},
            ],
        ),
    )
    assert result.document == document
    assert result.changes == []
    assert result.image_edit_intents[0].status == "not_started"
    assert result.image_edit_intents[0].source_asset_id == "original"


@pytest.mark.parametrize(
    "operation",
    [
        {"op": "replace_text", "block_id": "photo", "text": "오류"},
        {"op": "replace_text", "block_id": "unknown", "text": "오류"},
        {"op": "replace_image", "block_id": "photo", "asset_id": "unknown", "alt": "오류"},
        {"op": "replace_text", "block_id": "title", "text": "오류", "fact_refs": ["unknown"]},
        {"op": "remove_block", "block_id": "body"},
        {"op": "move_section", "section_id": "story", "index": 20},
        {
            "op": "replace_table",
            "block_id": "table",
            "rows": [{"label": "사이즈", "value": "XL", "fact_refs": ["size"]}],
        },
    ],
)
def test_failure_is_atomic(document, operation):
    before = document.model_dump()
    with pytest.raises(ValueError):
        preview_revision(
            document,
            proposal(
                document,
                [
                    {"op": "replace_text", "block_id": "title", "text": "먼저 변경"},
                    operation,
                ],
            ),
        )
    assert document.model_dump() == before


def test_clarification_and_conflict(document):
    request = proposal(document, [{"op": "remove_section", "section_id": "story"}])
    changed = document.model_copy(deep=True)
    changed.sections[0].blocks[0].content.text = "동시에 사용자가 고친 제목"
    with pytest.raises(RevisionConflict):
        preview_revision(changed, request)
    request.decision = "needs_clarification"
    request.operations = []
    request.question = "어느 사진을 바꿀까요?"
    result = preview_revision(document, request)
    assert result.document == document and result.question == request.question
    assert result.status == "needs_clarification"


def test_duplicate_ids_and_dangling_jobs_rejected(document):
    duplicate = document.sections[0].model_dump()
    with pytest.raises(ValueError):
        preview_revision(
            document,
            proposal(
                document,
                [
                    {"op": "add_section", "index": 0, "section": duplicate},
                ],
            ),
        )
    with pytest.raises(ValueError):
        preview_revision(
            document,
            proposal(
                document,
                [
                    {"op": "edit_image", "block_id": "photo", "instruction": "밝게"},
                    {"op": "remove_block", "block_id": "photo"},
                ],
            ),
        )


@pytest.mark.parametrize(
    "op",
    [
        {"op": "set_style", "block_id": "title"},
        {"op": "set_style", "block_id": "title", "color": "url(https://example.com)"},
        {"op": "set_style", "block_id": "title", "font_size": 999},
        {"op": "run_code", "code": "anything"},
    ],
)
def test_arbitrary_operations_and_styles_rejected(document, op):
    with pytest.raises(ValidationError):
        proposal(document, [op])


def test_http_preview_and_stale_version(document, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    body = {
        "document": document.model_dump(),
        "proposal": proposal(
            document,
            [
                {"op": "replace_text", "block_id": "body", "text": "<script>데이터</script>"},
            ],
        ).model_dump(),
    }
    original = deepcopy(body)
    response = client.post("/v1/detail-pages/revision-preview", json=body)
    assert response.status_code == 200
    assert response.json()["document"]["sections"][1]["blocks"][0]["content"]["text"].startswith(
        "<script>"
    )  # JSON 문자열로만 전달한다. 렌더러는 HTML 이스케이프가 필요하다.
    assert body == original and list(tmp_path.iterdir()) == []
    body["proposal"]["base_revision"] = 2
    assert client.post("/v1/detail-pages/revision-preview", json=body).status_code == 409


def test_render_preview_escapes_text_and_has_no_side_effects(document, tmp_path):
    before = document.model_dump()
    result = render_revision_preview(
        document,
        proposal(
            document,
            [
                {
                    "op": "replace_text",
                    "block_id": "title",
                    "text": "<script>상품 제목</script>",
                },
                {"op": "set_layout", "section_id": "hero", "layout": "image_right"},
            ],
        ),
        {
            "original": "assets/original.webp",
            "replacement": "assets/replacement.webp",
        },
    )

    assert result.preview.document.revision == 4
    assert "layout-image_right" in result.html
    assert "&lt;script&gt;상품 제목&lt;/script&gt;" in result.html
    assert "<script>상품 제목</script>" not in result.html
    assert result.html_sha256 == hashlib.sha256(result.html.encode()).hexdigest()
    assert result.model_calls == 0 and result.image_generation_calls == 0
    assert not result.persisted
    assert document.model_dump() == before
    assert list(tmp_path.iterdir()) == []


def test_render_preview_requires_exact_safe_asset_mapping(document):
    request = proposal(document, [{"op": "replace_text", "block_id": "title", "text": "수정"}])
    with pytest.raises(ValueError, match="정확히 일치"):
        render_revision_preview(document, request, {"original": "assets/original.webp"})
    with pytest.raises(ValueError, match="동일 출처 경로"):
        render_revision_preview(
            document,
            request,
            {"original": "../original.webp", "replacement": "assets/replacement.webp"},
        )


def test_render_preview_clarification_returns_no_html(document):
    request = proposal(document, [{"op": "replace_text", "block_id": "title", "text": "수정"}])
    request.decision = "needs_clarification"
    request.operations = []
    request.question = "어느 제목을 수정할까요?"
    result = render_revision_preview(document, request, {})
    assert result.preview.status == "needs_clarification"
    assert result.html is None and result.html_sha256 is None


def test_http_render_preview_returns_ready_html(document, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    body = {
        "document": document.model_dump(mode="json"),
        "proposal": proposal(
            document,
            [{"op": "replace_text", "block_id": "title", "text": "새 상품 제목"}],
        ).model_dump(mode="json"),
        "asset_urls": {
            "original": "assets/original.webp",
            "replacement": "assets/replacement.webp",
        },
    }

    response = client.post("/v1/detail-pages/revision-render-preview", json=body)

    assert response.status_code == 200
    result = response.json()
    assert "새 상품 제목" in result["html"]
    assert result["preview"]["document"]["revision"] == 4
    assert result["model_calls"] == 0
    assert list(tmp_path.iterdir()) == []

    body["asset_urls"]["original"] = "../secret.webp"
    assert client.post("/v1/detail-pages/revision-render-preview", json=body).status_code == 422

    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/detail-pages/revision-plan" in paths
    assert "/v1/detail-pages/revision-render-preview" in paths
