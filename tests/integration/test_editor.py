import copy
import io
import json

import pytest
from PIL import Image

from tests.integration.test_demo import _demo_client


@pytest.fixture
def editor(tmp_path, monkeypatch):
    root = tmp_path / "outputs"
    client = _demo_client(root, monkeypatch)
    source = tmp_path / "product.png"
    Image.new("RGB", (80, 100), "red").save(source)
    response = client.post(
        "/v1/generate",
        json={
            "request_id": "edit_test",
            "text": "딸기잼 300g",
            "image_path": str(source),
            "outputs": ["copy", "banner", "product_image"],
        },
    )
    assert response.status_code == 200
    return client, root / "edit_test"


def test_edit_preview_save_and_reopen_preserves_original(editor, monkeypatch):
    client, directory = editor
    original = (directory / "banner.png").read_bytes()
    metadata = (directory / "result.json").read_bytes()

    # 어떤 모델도 호출할 수 없는 상태에서도 편집 전체 흐름이 완주해야 합니다.
    def fail_model(*args, **kwargs):
        raise AssertionError("편집 중 모델 호출")

    monkeypatch.setattr(
        "ad_service.models.image_generator.MockImageProvider.generate_background", fail_model
    )
    monkeypatch.setattr("ad_service.models.vlm.MockCopyProvider.generate", fail_model)
    document = client.get("/v1/editor/edit_test/banner").json()
    assert document["product_editable"]
    scene = document["scene"]
    scene["text"]["headline"] = "새 제목"
    scene["product"]["y"] = 0.95
    preview = client.post("/v1/editor/edit_test/banner/preview", json=scene)
    assert preview.status_code == 200
    assert Image.open(io.BytesIO(preview.content)).size == (1536, 1024)
    saved = client.post("/v1/editor/edit_test/banner/save", json=scene)
    assert saved.status_code == 201
    result = saved.json()
    reopened = client.get(f"/v1/editor/edit_test/banner?revision={result['revision']}")
    assert reopened.json()["scene"] == scene
    downloaded = client.get(result["download_url"])
    assert downloaded.content == preview.content
    assert "attachment" in downloaded.headers["content-disposition"]
    assert (directory / "banner.png").read_bytes() == original
    assert (directory / "result.json").read_bytes() == metadata


def test_editor_disables_product_layer_for_direct_edit(editor):
    client, directory = editor
    result_path = directory / "result.json"
    data = json.loads(result_path.read_text())
    data["assets"][0]["details"] = {"input_strategy": "direct_edit"}
    result_path.write_text(json.dumps(data))
    Image.new("RGB", (1536, 1024), "purple").save(directory / "banner_reference_edit.png")
    document = client.get("/v1/editor/edit_test/banner").json()
    assert document["product_editable"] is False
    scene = document["scene"]
    first = client.post("/v1/editor/edit_test/banner/preview", json=scene)
    scene["product"]["x"] = 0
    assert client.post("/v1/editor/edit_test/banner/preview", json=scene).content == first.content


def test_editor_rejects_missing_layers_and_symlink_escape(editor, tmp_path):
    client, directory = editor
    background = directory / "banner_background.png"
    background.unlink()
    assert client.get("/v1/editor/edit_test/banner").status_code == 404
    external = tmp_path / "external.png"
    Image.new("RGB", (20, 20)).save(external)
    background.symlink_to(external)
    assert client.get("/v1/editor/edit_test/banner").status_code == 404
    (directory.parent / "linked").symlink_to(tmp_path, target_is_directory=True)
    assert client.get("/v1/editor/linked/banner").status_code == 404
    assert client.get("/v1/editor/jobs").json()["items"][0]["request_id"] == "edit_test"


def test_editor_rejects_invalid_placement_and_overflow(editor):
    client, _ = editor
    scene = client.get("/v1/editor/edit_test/banner").json()["scene"]
    invalid = copy.deepcopy(scene)
    invalid["product"]["height"] = 50
    assert client.post("/v1/editor/edit_test/banner/preview", json=invalid).status_code == 422
    scene["text"].update({"y": 0.85, "headline": "긴 문구 " * 15, "headline_size": 96})
    response = client.post("/v1/editor/edit_test/banner/save", json=scene)
    assert response.status_code == 422


def test_editor_empty_and_missing_results(tmp_path, monkeypatch):
    client = _demo_client(tmp_path / "empty", monkeypatch)
    assert client.get("/v1/editor/jobs").json() == {"items": []}
    assert client.get("/demo/editor").status_code == 200
    assert client.get("/v1/editor/missing/banner").status_code == 404
