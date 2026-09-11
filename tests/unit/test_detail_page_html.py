import pytest
from PIL import Image

from ad_service.api.schemas.revision import EditableDocument
from ad_service.rendering.detail_page_html import render_detail_page_html
from scripts.render_detail_page_html import run


@pytest.fixture
def document():
    return EditableDocument.model_validate(
        {
            "document_id": "detail_1",
            "revision": 2,
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
                    "section_id": "hero_01",
                    "kind": "hero",
                    "layout": "image_right",
                    "blocks": [
                        {
                            "content": {
                                "block_id": "heading_1",
                                "type": "text",
                                "role": "heading",
                                "text": "안전한 <상품>",
                            }
                        },
                        {
                            "content": {
                                "block_id": "image_1",
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


def test_renders_safe_long_page_structure(document):
    result = render_detail_page_html(document, {"front": "assets/front.webp"})
    assert "<!doctype html>" in result
    assert 'lang="ko"' in result
    assert 'data-document-id="detail_1"' in result
    assert 'data-revision="2"' in result
    assert 'data-section-id="hero_01"' in result
    assert 'data-block-id="heading_1"' in result
    assert "layout-image_right" in result
    assert "안전한 &lt;상품&gt;" in result
    assert "안전한 <상품>" not in result
    assert 'src="assets/front.webp"' in result
    assert ".layout-image_right .copy-column { grid-column:1; grid-row:1; }" in result
    assert ".layout-image_right .media-column { grid-column:1; grid-row:2; }" in result
    assert "<script" not in result


def test_missing_or_unsafe_asset_path_fails(document):
    with pytest.raises(ValueError, match="자산 경로"):
        render_detail_page_html(document, {})
    with pytest.raises(ValueError, match="동일 출처 경로"):
        render_detail_page_html(document, {"front": "../secret.webp"})
    with pytest.raises(ValueError, match="동일 출처 경로"):
        render_detail_page_html(document, {"front": "javascript:alert(1)"})
    assert 'src="/v1/assets/front.webp"' in render_detail_page_html(
        document, {"front": "/v1/assets/front.webp"}
    )


def test_export_writes_self_contained_artifacts(document, tmp_path):
    result_path = tmp_path / "result.json"
    result_path.write_text(
        '{"document":' + document.model_dump_json() + "}",
        encoding="utf-8",
    )
    image_path = tmp_path / "source.webp"
    Image.new("RGB", (1000, 1000), "red").save(image_path)
    output = tmp_path / "rendered"

    index = run(result_path, {"front": image_path}, output)

    assert index.is_file()
    assert (output / "document.json").is_file()
    assert (output / "manifest.json").is_file()
    assert (output / "assets" / "front.webp").is_file()
