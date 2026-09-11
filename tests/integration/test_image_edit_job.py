from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from ad_service.api.schemas.image_edit_job import CreateImageEditJobRequest
from ad_service.api.schemas.revision import EditableDocument, RevisionProposal
from ad_service.pipelines.image_edit_job import create_image_edit_job
from ad_service.pipelines.revision import document_hash, render_revision_preview
from tests.integration.test_demo import _demo_client


@pytest.fixture
def image_edit_store(tmp_path, monkeypatch):
    output_root = tmp_path / "outputs"
    source_dir = output_root / "source_run"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "front.png"
    Image.new("RGB", (300, 200), "#a52a2a").save(source_path)

    client = _demo_client(output_root, monkeypatch)
    document = EditableDocument.model_validate(
        {
            "document_id": "image_edit_product",
            "revision": 1,
            "assets": [
                {
                    "asset_id": "front",
                    "role": "primary_product",
                    "width": 300,
                    "height": 200,
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
                                "block_id": "photo",
                                "type": "image",
                                "source_asset_id": "front",
                                "alt": "상품 사진",
                            }
                        },
                        {
                            "content": {
                                "block_id": "title",
                                "type": "text",
                                "role": "heading",
                                "text": "원본 제목",
                            }
                        },
                    ],
                }
            ],
        }
    )
    registration = client.post(
        "/v1/detail-pages/documents",
        json={
            "operation_id": "register_image_edit_product",
            "document": document.model_dump(mode="json"),
            "asset_urls": {"front": "/v1/results/source_run/front.png"},
        },
    )
    assert registration.status_code == 201
    return client, output_root, source_path, document


def _create_body(document, job_id="edit_job_001"):
    return {
        "job_id": job_id,
        "base_revision": document.revision,
        "base_document_sha256": document_hash(document),
        "intent": {
            "block_id": "photo",
            "source_asset_id": "front",
            "instruction": "배경만 밝은 베이지색으로 바꿔줘",
            "status": "not_started",
        },
        "seed": 7,
    }


def _approval(created, operation_id="approve_edit_job_001"):
    return {
        "operation_id": operation_id,
        "approval_sha256": created["approval_sha256"],
        "approved_cost_cap_usd": created["estimated_cost_usd"],
    }


def _execute(client, document, job_id):
    created = client.post(
        "/v1/detail-pages/documents/image_edit_product/image-edit-jobs",
        json=_create_body(document, job_id),
    ).json()
    executed = client.post(
        f"/v1/detail-pages/image-edit-jobs/{job_id}/approve",
        json=_approval(created, f"approve_{job_id}"),
    )
    assert executed.status_code == 200
    return executed.json()


def test_job_registration_does_not_call_model_or_create_image(image_edit_store):
    client, output_root, _, document = image_edit_store

    created = client.post(
        "/v1/detail-pages/documents/image_edit_product/image-edit-jobs",
        json=_create_body(document),
    )

    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending_approval"
    assert body["approval_required"] is True
    assert body["model_calls"] == 0
    assert body["image_generation_calls"] == 0
    assert body["provider"] == "mock"
    assert body["output_size"] == "1536x1024"
    assert "배경만 밝은 베이지색" in body["prompt"]
    job_dir = output_root / "detail-page-image-edits" / "edit_job_001"
    assert (job_dir / "job.json").is_file()
    assert not (job_dir / "result.png").exists()

    replay = client.post(
        "/v1/detail-pages/documents/image_edit_product/image-edit-jobs",
        json=_create_body(document),
    )
    assert replay.status_code == 201
    assert replay.json()["replayed"] is True

    changed = _create_body(document)
    changed["intent"]["instruction"] = "전혀 다른 요청"
    assert (
        client.post(
            "/v1/detail-pages/documents/image_edit_product/image-edit-jobs",
            json=changed,
        ).status_code
        == 409
    )


def test_approval_executes_once_and_result_is_readable(image_edit_store):
    client, output_root, _, document = image_edit_store
    created = client.post(
        "/v1/detail-pages/documents/image_edit_product/image-edit-jobs",
        json=_create_body(document, "edit_job_run"),
    ).json()
    approval = _approval(created, "approve_edit_job_run")

    executed = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_run/approve",
        json=approval,
    )

    assert executed.status_code == 200
    body = executed.json()
    assert body["status"] == "succeeded"
    assert body["approval_required"] is False
    assert body["model_calls"] == 1
    assert body["image_generation_calls"] == 1
    assert body["result_asset_id"].startswith("front_edit_")
    assert body["result_asset_url"].endswith("/edit_job_run/result")
    assert (output_root / "detail-page-image-edits" / "edit_job_run" / "result.png").is_file()

    image = client.get(body["result_asset_url"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content.startswith(b"\x89PNG")

    replay = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_run/approve",
        json=approval,
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True

    different_approval = _approval(created, "different_approval")
    conflict = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_run/approve",
        json=different_approval,
    )
    assert conflict.status_code == 409


def test_wrong_approval_or_changed_source_never_calls_model(image_edit_store):
    client, output_root, source_path, document = image_edit_store
    created = client.post(
        "/v1/detail-pages/documents/image_edit_product/image-edit-jobs",
        json=_create_body(document, "edit_job_guard"),
    ).json()
    wrong = _approval(created)
    wrong["approval_sha256"] = "0" * 64

    response = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_guard/approve",
        json=wrong,
    )

    assert response.status_code == 409
    job = client.get("/v1/detail-pages/image-edit-jobs/edit_job_guard").json()
    assert job["status"] == "pending_approval"
    assert job["model_calls"] == 0
    assert not (output_root / "detail-page-image-edits" / "edit_job_guard" / "result.png").exists()

    Image.new("RGB", (300, 200), "#ffffff").save(source_path)
    changed_source = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_guard/approve",
        json=_approval(created),
    )
    assert changed_source.status_code == 409
    assert "원본 이미지" in changed_source.json()["detail"]


def test_stale_document_and_unmanaged_asset_are_rejected(image_edit_store):
    client, _, _, document = image_edit_store
    created = client.post(
        "/v1/detail-pages/documents/image_edit_product/image-edit-jobs",
        json=_create_body(document, "edit_job_stale"),
    ).json()

    proposal = {
        "request_id": "change_document_before_image",
        "base_revision": 1,
        "base_sha256": document_hash(document),
        "instruction": "제목을 바꿔줘",
        "decision": "ready",
        "operations": [{"op": "replace_text", "block_id": "title", "text": "새 제목"}],
    }
    rendered = render_revision_preview(
        document,
        RevisionProposal.model_validate(proposal),
        {"front": "/v1/results/source_run/front.png"},
    )
    approved = client.post(
        "/v1/detail-pages/documents/image_edit_product/approve",
        json={
            "operation_id": "approve_text_before_image",
            "proposal": proposal,
            "approved_document_sha256": rendered.preview.document_sha256,
            "approved_html_sha256": rendered.html_sha256,
        },
    )
    assert approved.status_code == 201

    stale = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_stale/approve",
        json=_approval(created),
    )
    assert stale.status_code == 409
    assert "문서가 변경" in stale.json()["detail"]


def test_same_approval_is_idempotent_under_concurrency(image_edit_store):
    client, _, _, document = image_edit_store
    created = client.post(
        "/v1/detail-pages/documents/image_edit_product/image-edit-jobs",
        json=_create_body(document, "edit_job_concurrent"),
    ).json()
    approval = _approval(created, "approve_concurrent")

    def approve():
        return client.post(
            "/v1/detail-pages/image-edit-jobs/edit_job_concurrent/approve",
            json=approval,
        ).json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: approve(), range(2)))

    assert [item["status"] for item in results] == ["succeeded", "succeeded"]
    assert sorted(item["replayed"] for item in results) == [False, True]


def test_cost_cap_is_checked_before_real_provider_is_created(image_edit_store):
    client, output_root, _, document = image_edit_store
    request = CreateImageEditJobRequest.model_validate(
        _create_body(document, "edit_job_paid_quote")
    )
    created = create_image_edit_job(
        "image_edit_product",
        request,
        output_root,
        "gpt-image-2",
        "low",
    ).model_dump(mode="json")
    assert created["estimated_cost_usd"] > 0

    rejected = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_paid_quote/approve",
        json={
            "operation_id": "reject_paid_quote",
            "approval_sha256": created["approval_sha256"],
            "approved_cost_cap_usd": 0,
        },
    )

    assert rejected.status_code == 409
    status = client.get("/v1/detail-pages/image-edit-jobs/edit_job_paid_quote").json()
    assert status["status"] == "pending_approval"
    assert status["model_calls"] == 0


def test_unmanaged_asset_url_cannot_be_used_as_server_file(image_edit_store):
    client, _, _, document = image_edit_store
    unmanaged = document.model_copy(deep=True)
    unmanaged.document_id = "unmanaged_asset_product"
    registered = client.post(
        "/v1/detail-pages/documents",
        json={
            "operation_id": "register_unmanaged_asset",
            "document": unmanaged.model_dump(mode="json"),
            "asset_urls": {"front": "/v1/assets/front.png"},
        },
    )
    assert registered.status_code == 201

    response = client.post(
        "/v1/detail-pages/documents/unmanaged_asset_product/image-edit-jobs",
        json=_create_body(unmanaged, "edit_job_unmanaged"),
    )

    assert response.status_code == 422
    assert "/v1/results" in response.json()["detail"]


def test_reviewed_result_becomes_new_asset_and_immutable_revision(image_edit_store):
    client, _, _, document = image_edit_store
    executed = _execute(client, document, "edit_job_attach")

    preview_response = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_attach/attachment-preview"
    )

    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["status"] == "needs_review"
    assert preview["persisted"] is False
    assert preview["model_calls"] == 0
    assert preview["image_generation_calls"] == 0
    assert preview["document"]["revision"] == 2
    assert preview["result_asset_id"] == executed["result_asset_id"]
    assert executed["result_asset_url"] in preview["html"]
    image_block = preview["document"]["sections"][0]["blocks"][0]["content"]
    assert image_block["source_asset_id"] == executed["result_asset_id"]

    current_before = client.get("/v1/detail-pages/documents/image_edit_product").json()
    assert current_before["document"]["revision"] == 1

    approval = {
        "operation_id": "attach_edit_job_001",
        "approved_document_sha256": preview["document_sha256"],
        "approved_html_sha256": preview["html_sha256"],
        "approved_result_file_sha256": preview["result_file_sha256"],
    }
    attached = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_attach/attach",
        json=approval,
    )

    assert attached.status_code == 201
    assert attached.json()["revision"] == 2
    assert attached.json()["model_calls"] == 0
    current = client.get("/v1/detail-pages/documents/image_edit_product").json()
    assert current["document"]["revision"] == 2
    assert current["asset_urls"][executed["result_asset_id"]] == executed["result_asset_url"]
    assert (
        current["document"]["sections"][0]["blocks"][0]["content"]["source_asset_id"]
        == executed["result_asset_id"]
    )
    original = client.get(
        "/v1/detail-pages/documents/image_edit_product/revisions/1/document"
    ).json()
    assert original == document.model_dump(mode="json")

    job = client.get("/v1/detail-pages/image-edit-jobs/edit_job_attach").json()
    assert job["attached_revision"] == 2
    assert job["attachment_operation_id"] == "attach_edit_job_001"
    replay = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_attach/attach",
        json=approval,
    )
    assert replay.status_code == 201
    assert replay.json()["replayed"] is True
    history = client.get("/v1/detail-pages/documents/image_edit_product/revisions").json()
    assert [item["revision"] for item in history["items"]] == [2, 1]


def test_attachment_requires_completed_job_and_exact_review_hashes(image_edit_store):
    client, output_root, _, document = image_edit_store
    pending = client.post(
        "/v1/detail-pages/documents/image_edit_product/image-edit-jobs",
        json=_create_body(document, "edit_job_pending_attach"),
    )
    assert pending.status_code == 201
    assert (
        client.post(
            "/v1/detail-pages/image-edit-jobs/edit_job_pending_attach/attachment-preview"
        ).status_code
        == 409
    )

    _execute(client, document, "edit_job_tamper_attach")
    preview = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_tamper_attach/attachment-preview"
    ).json()
    wrong = {
        "operation_id": "attach_wrong_hash",
        "approved_document_sha256": preview["document_sha256"],
        "approved_html_sha256": preview["html_sha256"],
        "approved_result_file_sha256": "0" * 64,
    }
    rejected = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_tamper_attach/attach",
        json=wrong,
    )
    assert rejected.status_code == 409
    assert (
        client.get("/v1/detail-pages/documents/image_edit_product").json()["document"]["revision"]
        == 1
    )

    result_path = output_root / "detail-page-image-edits" / "edit_job_tamper_attach" / "result.png"
    Image.new("RGB", (1536, 1024), "#000000").save(result_path)
    exact_review = dict(wrong)
    exact_review["operation_id"] = "attach_tampered_file"
    exact_review["approved_result_file_sha256"] = preview["result_file_sha256"]
    tampered = client.post(
        "/v1/detail-pages/image-edit-jobs/edit_job_tamper_attach/attach",
        json=exact_review,
    )
    assert tampered.status_code == 409
    assert "결과 파일" in tampered.json()["detail"]
