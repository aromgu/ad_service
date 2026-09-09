from PIL import Image, ImageDraw

from ad_service.api.schemas.generation import (
    BoundingBox,
    GenerationRequest,
    ImageProcessingRoute,
)
from ad_service.models.base import BackgroundRemover
from ad_service.models.image_generator import MockImageProvider
from ad_service.models.vlm import MockCopyProvider
from ad_service.pipelines.inference import GenerationPipeline
from ad_service.pipelines.preprocessing import AutoBackgroundRemover, SimpleBackgroundRemover


class FailingBackgroundRemover(BackgroundRemover):
    """직접 편집 실험에서 배경 제거가 호출되면 테스트를 실패시킵니다."""

    name = "must-not-run"

    def remove(self, image_path, bbox):
        raise AssertionError("direct_edit에서는 배경 제거를 호출하면 안 됩니다")


class RecordingBackgroundRemover(BackgroundRemover):
    """자동 라우터가 어떤 제거기를 골랐는지 기록하는 가벼운 테스트 대역입니다."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.call_count = 0

    def remove(self, image_path, bbox):
        self.call_count += 1
        del bbox
        return Image.open(image_path).convert("RGBA")


def test_mock_pipeline_creates_four_required_outputs(tmp_path) -> None:
    source = tmp_path / "product.jpg"
    image = Image.new("RGB", (500, 500), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((150, 80, 350, 430), radius=20, fill=(90, 50, 160))
    image.save(source)
    request = GenerationRequest(
        request_id="snack_001",
        product_name="테스트 과자",
        category="식품/과자",
        features=["바삭한 식감", "고소한 맛"],
        target_audience="간식을 찾는 소비자",
        tone="밝고 친근함",
        product_image_path=str(source),
        product_bbox=BoundingBox(xmin=150, ymin=80, xmax=350, ymax=430),
    )
    pipeline = GenerationPipeline(
        copy_provider=MockCopyProvider(),
        image_provider=MockImageProvider(),
        background_remover=SimpleBackgroundRemover(max_side=256),
        output_root=tmp_path / "outputs",
    )
    result = pipeline.generate(request)
    assert len(result.assets) == 3
    assert len(result.copy_result.headline_candidates) == 3
    assert result.metrics.copy_latency_ms == 1
    assert result.metrics.copy_input_tokens == 0
    assert result.metrics.copy_output_tokens == 0
    assert result.metrics.copy_details == {}
    assert all(asset.details == {} for asset in result.assets)
    assert all(
        (tmp_path / "outputs/snack_001" / f"{asset.type.value}.png").is_file()
        for asset in result.assets
    )
    assert (tmp_path / "outputs/snack_001/result.json").is_file()


def test_direct_edit_bypasses_background_removal(tmp_path) -> None:
    """직접 편집을 선택하면 BiRefNet 합성 경로를 거치지 않아야 합니다."""

    source = tmp_path / "product.jpg"
    Image.new("RGB", (300, 400), "purple").save(source)
    request = GenerationRequest(
        request_id="direct_edit_001",
        text="원본 상품을 유지한 스튜디오 광고 사진",
        image_path=str(source),
        outputs=["product_image"],
        options={"image_input_strategy": "direct_edit"},
    )
    pipeline = GenerationPipeline(
        copy_provider=MockCopyProvider(),
        image_provider=MockImageProvider(),
        background_remover=FailingBackgroundRemover(),
        output_root=tmp_path / "direct_outputs",
    )

    result = pipeline.generate(request)

    assert result.metrics.background_remover is None
    assert result.metrics.image_processing_route is ImageProcessingRoute.DIRECT_EDIT
    assert "사용자가 direct_edit를 명시" in result.metrics.routing_reason
    assert result.assets[0].details["input_strategy"] == "direct_edit"
    assert (tmp_path / "direct_outputs/direct_edit_001/product_image.png").is_file()
    assert (
        tmp_path / "direct_outputs/direct_edit_001/product_image_reference_edit.png"
    ).is_file()


def test_auto_route_uses_birefnet_without_bbox(tmp_path) -> None:
    """단순 상품 사진에는 박스 없이 BiRefNet 합성 경로를 자동 선택합니다."""

    source = tmp_path / "single_product.jpg"
    Image.new("RGB", (300, 400), "purple").save(source)
    birefnet = RecordingBackgroundRemover("birefnet-stub")
    sam2 = RecordingBackgroundRemover("sam2-stub")
    pipeline = GenerationPipeline(
        copy_provider=MockCopyProvider(),
        image_provider=MockImageProvider(),
        background_remover=AutoBackgroundRemover(birefnet=birefnet, sam2=sam2),
        output_root=tmp_path / "auto_birefnet",
    )
    request = GenerationRequest(
        request_id="auto_birefnet_001",
        image_path=str(source),
        outputs=["product_image"],
    )

    result = pipeline.generate(request)

    assert birefnet.call_count == 1
    assert sam2.call_count == 0
    assert result.metrics.image_processing_route is ImageProcessingRoute.COMPOSITE
    assert result.metrics.background_remover == "birefnet-stub"
    assert "선택 박스가 없어 BiRefNet" in result.metrics.routing_reason


def test_auto_route_uses_sam2_with_bbox(tmp_path) -> None:
    """복잡한 사진에서 사용자가 박스를 지정하면 SAM2 합성 경로를 자동 선택합니다."""

    source = tmp_path / "shelf.jpg"
    Image.new("RGB", (300, 400), "red").save(source)
    birefnet = RecordingBackgroundRemover("birefnet-stub")
    sam2 = RecordingBackgroundRemover("sam2-stub")
    pipeline = GenerationPipeline(
        copy_provider=MockCopyProvider(),
        image_provider=MockImageProvider(),
        background_remover=AutoBackgroundRemover(birefnet=birefnet, sam2=sam2),
        output_root=tmp_path / "auto_sam2",
    )
    request = GenerationRequest(
        request_id="auto_sam2_001",
        image_path=str(source),
        image_bbox=BoundingBox(xmin=50, ymin=80, xmax=250, ymax=350),
        outputs=["product_image"],
    )

    result = pipeline.generate(request)

    assert birefnet.call_count == 0
    assert sam2.call_count == 1
    assert result.metrics.image_processing_route is ImageProcessingRoute.COMPOSITE
    assert result.metrics.background_remover == "sam2-stub"
    assert "선택 박스가 있어 SAM2" in result.metrics.routing_reason


def test_text_to_image_route_does_not_run_a_remover(tmp_path) -> None:
    """이미지가 없는 요청은 배경 제거 없이 설명 기반 생성으로 바로 이동합니다."""

    birefnet = RecordingBackgroundRemover("birefnet-stub")
    sam2 = RecordingBackgroundRemover("sam2-stub")
    pipeline = GenerationPipeline(
        copy_provider=MockCopyProvider(),
        image_provider=MockImageProvider(),
        background_remover=AutoBackgroundRemover(birefnet=birefnet, sam2=sam2),
        output_root=tmp_path / "text_to_image",
    )
    request = GenerationRequest(
        request_id="text_to_image_001",
        text="수제 딸기잼의 밝은 아침 광고 장면",
        outputs=["banner"],
    )

    result = pipeline.generate(request)

    assert birefnet.call_count == 0
    assert sam2.call_count == 0
    assert result.metrics.image_processing_route is ImageProcessingRoute.TEXT_TO_IMAGE
    assert result.metrics.background_remover is None
