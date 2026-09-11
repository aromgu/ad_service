import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from ad_service.api.schemas.revision import EditableDocument, RevisionProposal
from ad_service.pipelines.revision import document_hash, render_revision_preview
from tests.integration.test_demo import _demo_client


@pytest.fixture
def document():
    return EditableDocument.model_validate(
        {
            "document_id": "stored_cosmetics",
            "revision": 1,
            "assets": [
                {
                    "asset_id": "front",
                    "role": "primary_product",
                    "width": 1000,
                    "height": 1000,
                }
            ],
            "sections": [
                {
                    "section_id": "hero",
                    "kind": "hero",
                    "layout": "stack",
                    "blocks": [
                        {
                            "content": {
                                "block_id": "title",
                                "type": "text",
                                "role": "heading",
                                "text": "<script>원본 제목</script>",
                            }
                        },
                        {
                            "content": {
                                "block_id": "photo",
                                "type": "image",
                                "source_asset_id": "front",
                                "alt": "상품 사진",
                            }
                        },
                    ],
                }
            ],
        }
    )


@pytest.fixture
def store(tmp_path, monkeypatch, document):
    client = _demo_client(tmp_path / "outputs", monkeypatch)
    request = {
        "operation_id": "register_cosmetics_001",
        "document": document.model_dump(mode="json"),
        "asset_urls": {"front": "/v1/assets/front.webp"},
    }
    response = client.post("/v1/detail-pages/documents", json=request)
    assert response.status_code == 201
    return client, tmp_path / "outputs", request


def proposal(document, operations, request_id="approve_test"):
    return RevisionProposal.model_validate(
        {
            "request_id": request_id,
            "base_revision": document.revision,
            "base_sha256": document_hash(document),
            "instruction": "선택한 부분만 수정해줘",
            "decision": "ready",
            "operations": operations,
        }
    )


def approval_body(document, revision_proposal, operation_id, asset_urls=None):
    rendered = render_revision_preview(
        document,
        revision_proposal,
        asset_urls or {"front": "/v1/assets/front.webp"},
    )
    return {
        "operation_id": operation_id,
        "proposal": revision_proposal.model_dump(mode="json"),
        "approved_document_sha256": rendered.preview.document_sha256,
        "approved_html_sha256": rendered.html_sha256,
    }


def test_register_read_and_immutable_html(store, document):
    client, output_root, request = store
    current = client.get("/v1/detail-pages/documents/stored_cosmetics")
    assert current.status_code == 200
    assert current.json()["document"] == document.model_dump(mode="json")
    assert current.json()["persisted"] is True

    html = client.get("/v1/detail-pages/documents/stored_cosmetics/revisions/1/html")
    assert html.status_code == 200
    assert "&lt;script&gt;원본 제목&lt;/script&gt;" in html.text
    assert "<script>원본 제목</script>" not in html.text
    assert "default-src 'none'" in html.headers["content-security-policy"]
    assert html.headers["x-content-type-options"] == "nosniff"

    saved = output_root / "detail-pages" / "stored_cosmetics" / "revisions" / "00000001"
    assert (saved / "document.json").is_file()
    assert (saved / "index.html").is_file()
    assert (saved / "metadata.json").is_file()

    replay = client.post("/v1/detail-pages/documents", json=request)
    assert replay.status_code == 201 and replay.json()["replayed"] is True
    duplicate = json.loads(json.dumps(request))
    duplicate["operation_id"] = "different_registration"
    assert client.post("/v1/detail-pages/documents", json=duplicate).status_code == 409


def test_approved_revision_is_saved_once_and_history_preserves_original(store, document):
    client, _, _ = store
    revision_proposal = proposal(
        document,
        [
            {"op": "replace_text", "block_id": "title", "text": "승인한 새 제목"},
            {"op": "set_layout", "section_id": "hero", "layout": "image_right"},
        ],
    )
    body = approval_body(document, revision_proposal, "approve_cosmetics_001")

    saved = client.post("/v1/detail-pages/documents/stored_cosmetics/approve", json=body)

    assert saved.status_code == 201
    assert saved.json()["revision"] == 2
    assert saved.json()["replayed"] is False
    assert saved.json()["model_calls"] == 0
    current = client.get("/v1/detail-pages/documents/stored_cosmetics").json()
    assert current["document"]["revision"] == 2
    assert current["document"]["sections"][0]["layout"] == "image_right"
    assert current["document"]["sections"][0]["blocks"][0]["content"]["text"] == "승인한 새 제목"

    original = client.get("/v1/detail-pages/documents/stored_cosmetics/revisions/1/document").json()
    assert original == document.model_dump(mode="json")
    history = client.get("/v1/detail-pages/documents/stored_cosmetics/revisions").json()
    assert [item["revision"] for item in history["items"]] == [2, 1]
    assert history["current_revision"] == 2

    replay = client.post("/v1/detail-pages/documents/stored_cosmetics/approve", json=body)
    assert replay.status_code == 201 and replay.json()["replayed"] is True
    assert (
        len(client.get("/v1/detail-pages/documents/stored_cosmetics/revisions").json()["items"])
        == 2
    )


def test_stale_or_unapproved_revision_never_changes_current(store, document):
    client, _, _ = store
    first_proposal = proposal(
        document,
        [{"op": "replace_text", "block_id": "title", "text": "버전 2"}],
    )
    first = approval_body(document, first_proposal, "approve_first")
    assert (
        client.post("/v1/detail-pages/documents/stored_cosmetics/approve", json=first).status_code
        == 201
    )

    stale = approval_body(document, first_proposal, "approve_stale")
    assert (
        client.post("/v1/detail-pages/documents/stored_cosmetics/approve", json=stale).status_code
        == 409
    )

    current_document = EditableDocument.model_validate(
        client.get("/v1/detail-pages/documents/stored_cosmetics").json()["document"]
    )
    second_proposal = proposal(
        current_document,
        [{"op": "replace_text", "block_id": "title", "text": "버전 3"}],
    )
    wrong_hash = approval_body(current_document, second_proposal, "approve_wrong_hash")
    wrong_hash["approved_html_sha256"] = "0" * 64
    assert (
        client.post(
            "/v1/detail-pages/documents/stored_cosmetics/approve", json=wrong_hash
        ).status_code
        == 409
    )

    current = client.get("/v1/detail-pages/documents/stored_cosmetics").json()
    assert current["document"]["revision"] == 2
    assert (
        len(client.get("/v1/detail-pages/documents/stored_cosmetics/revisions").json()["items"])
        == 2
    )


def test_pending_image_edit_and_idempotency_mismatch_are_rejected(store, document):
    client, _, _ = store
    image_proposal = proposal(
        document,
        [{"op": "edit_image", "block_id": "photo", "instruction": "배경만 밝게"}],
    )
    image_body = approval_body(document, image_proposal, "approve_image_pending")
    response = client.post(
        "/v1/detail-pages/documents/stored_cosmetics/approve",
        json=image_body,
    )
    assert response.status_code == 409
    assert "이미지 편집" in response.json()["detail"]

    text_proposal = proposal(
        document,
        [{"op": "replace_text", "block_id": "title", "text": "첫 승인"}],
    )
    first = approval_body(document, text_proposal, "same_operation")
    assert (
        client.post("/v1/detail-pages/documents/stored_cosmetics/approve", json=first).status_code
        == 201
    )

    changed = json.loads(json.dumps(first))
    changed["approved_html_sha256"] = "f" * 64
    conflict = client.post(
        "/v1/detail-pages/documents/stored_cosmetics/approve",
        json=changed,
    )
    assert conflict.status_code == 409
    assert "operation_id" in conflict.json()["detail"]


def test_simultaneous_approvals_cannot_overwrite_each_other(store, document):
    client, _, _ = store
    first_proposal = proposal(
        document,
        [{"op": "replace_text", "block_id": "title", "text": "동시 요청 A"}],
        request_id="concurrent_a",
    )
    second_proposal = proposal(
        document,
        [{"op": "replace_text", "block_id": "title", "text": "동시 요청 B"}],
        request_id="concurrent_b",
    )
    bodies = [
        approval_body(document, first_proposal, "concurrent_operation_a"),
        approval_body(document, second_proposal, "concurrent_operation_b"),
    ]

    def approve(body):
        return client.post(
            "/v1/detail-pages/documents/stored_cosmetics/approve",
            json=body,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(approve, bodies))

    assert sorted(statuses) == [201, 409]
    current = client.get("/v1/detail-pages/documents/stored_cosmetics").json()
    assert current["document"]["revision"] == 2
    history = client.get("/v1/detail-pages/documents/stored_cosmetics/revisions").json()
    assert [item["revision"] for item in history["items"]] == [2, 1]


def test_invalid_paths_and_missing_documents_fail_closed(tmp_path, monkeypatch, document):
    client = _demo_client(tmp_path / "outputs", monkeypatch)
    body = {
        "operation_id": "unsafe_asset",
        "document": document.model_dump(mode="json"),
        "asset_urls": {"front": "https://outside.example/front.webp"},
    }
    assert client.post("/v1/detail-pages/documents", json=body).status_code == 422
    assert client.get("/v1/detail-pages/documents/missing").status_code == 404
    assert client.get("/v1/detail-pages/documents/bad.name").status_code == 404
