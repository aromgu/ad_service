from ad_service.api.schemas.generation import AssetType, GenerationRequest, OutputType
from ad_service.prompts.templates import build_copy_prompt, build_image_prompt


def _targeted_request() -> GenerationRequest:
    return GenerationRequest(
        request_id="prompt_001",
        text="지역 농산물로 만든 수제 딸기잼",
        outputs=[OutputType.COPY, OutputType.BANNER],
        options={
            "product_category": "packaged_food",
            "sales_channel": "smart_store",
            "campaign_goal": "product_launch",
            "target_audience": "지역 먹거리에 관심 있는 30대",
            "tone": "따뜻하고 신뢰감 있는",
            "copy_style": "emotional",
            "copy_length": "short",
            "must_include": ["국산 딸기"],
            "avoid_phrases": ["최고"],
        },
    )


def test_copy_prompt_contains_target_choices() -> None:
    """문구 모델이 업종과 선택 조건을 빠뜨리지 않고 받는지 확인합니다."""

    prompt = build_copy_prompt(_targeted_request())

    assert "식료품 소매업" in prompt
    assert "가공·포장식품" in prompt
    assert "스마트스토어" in prompt
    assert "신상품 소개" in prompt
    assert "공감할 사용 장면" in prompt
    assert "헤드라인 8~16자" in prompt
    assert "반드시 포함할 표현: 국산 딸기" in prompt
    assert "사용하지 않을 표현: 최고" in prompt
    assert "이모지: 사용 금지" in prompt


def test_image_prompt_contains_target_choices() -> None:
    """이미지 모델에도 문구 모델과 동일한 광고 환경을 전달합니다."""

    prompt = build_image_prompt(_targeted_request(), AssetType.BANNER)

    assert "식료품 소매업" in prompt
    assert "가공·포장식품" in prompt
    assert "스마트스토어" in prompt
    assert "신상품 소개" in prompt
