from PIL import Image, ImageDraw

from ad_service.api.schemas.generation import BoundingBox, GenerationRequest
from ad_service.models.image_generator import MockImageProvider
from ad_service.models.vlm import MockCopyProvider
from ad_service.pipelines.inference import GenerationPipeline
from ad_service.pipelines.preprocessing import SimpleBackgroundRemover


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
