from pathlib import Path

import pytest
from pydantic import ValidationError

from ad_service.api.schemas.generation import (
    BoundingBox,
    CampaignGoal,
    CopyLength,
    CopyResult,
    CopyStyle,
    GenerationRequest,
    ImageInputStrategy,
    InputMode,
    OutputType,
    ProductCategory,
    SalesChannel,
)


def test_text_only_request_is_allowed() -> None:
    """이미지 없이도 문구와 이미지를 요청할 수 있어야 합니다."""

    request = GenerationRequest(
        request_id="text_001",
        text="폐현수막을 재활용해 만든 업사이클링 파우치",
        outputs=[OutputType.COPY, OutputType.BANNER],
    )

    assert request.input_mode is InputMode.TEXT_ONLY
    assert request.resolved_image_path() is None


def test_image_only_request_is_allowed() -> None:
    """설명 없이 사진만 넣어 이미지 편집을 요청할 수 있어야 합니다."""

    request = GenerationRequest(
        request_id="image_001",
        image_path="data/sample.jpg",
        outputs=[OutputType.PRODUCT_IMAGE],
    )

    assert request.input_mode is InputMode.IMAGE_ONLY
    assert request.resolved_image_path(Path("/project")) == Path("/project/data/sample.jpg")


def test_text_and_image_request_is_allowed() -> None:
    """텍스트 지시와 제품 사진을 함께 보내는 편집 요청도 허용합니다."""

    request = GenerationRequest(
        request_id="edit_001",
        text="제품은 유지하고 따뜻한 카페 배경으로 바꿔줘",
        image_path="data/sample.jpg",
        outputs=[OutputType.BANNER],
    )

    assert request.input_mode is InputMode.TEXT_AND_IMAGE


def test_direct_edit_requires_and_keeps_image_input() -> None:
    """직접 편집 방식은 원본 이미지가 있을 때만 선택할 수 있어야 합니다."""

    request = GenerationRequest(
        request_id="direct_edit_001",
        text="상품은 유지하고 스튜디오 배경으로 바꿔줘",
        image_path="data/sample.jpg",
        outputs=[OutputType.PRODUCT_IMAGE],
        options={"image_input_strategy": "direct_edit"},
    )

    assert request.options.image_input_strategy is ImageInputStrategy.DIRECT_EDIT

    with pytest.raises(ValidationError):
        GenerationRequest(
            request_id="direct_edit_without_image",
            text="스튜디오 광고 이미지",
            outputs=[OutputType.PRODUCT_IMAGE],
            options={"image_input_strategy": "direct_edit"},
        )


def test_food_retail_target_options_are_allowed() -> None:
    """선택 화면의 카테고리·채널·광고 목적 값이 요청 모델에 저장되어야 합니다."""

    request = GenerationRequest(
        request_id="target_001",
        text="수제 딸기잼 신상품 광고",
        outputs=[OutputType.COPY],
        options={
            "product_category": "packaged_food",
            "sales_channel": "smart_store",
            "campaign_goal": "product_launch",
        },
    )

    assert request.options.product_category is ProductCategory.PACKAGED_FOOD
    assert request.options.sales_channel is SalesChannel.SMART_STORE
    assert request.options.campaign_goal is CampaignGoal.PRODUCT_LAUNCH


def test_copy_preferences_are_allowed() -> None:
    """스타일과 사용자 표현 조건이 공통 요청에 저장되어야 합니다."""

    request = GenerationRequest(
        request_id="style_001",
        text="국산 딸기로 만든 수제 딸기잼",
        outputs=[OutputType.COPY],
        options={
            "copy_style": "emotional",
            "copy_length": "short",
            "must_include": ["국산 딸기"],
            "avoid_phrases": ["최고"],
        },
    )

    assert request.options.copy_style is CopyStyle.EMOTIONAL
    assert request.options.copy_length is CopyLength.SHORT


def test_custom_style_requires_instruction() -> None:
    """직접 입력을 선택했다면 모델이 따를 구체적인 설명도 필요합니다."""

    with pytest.raises(ValidationError):
        GenerationRequest(
            request_id="custom_001",
            text="수제 딸기잼",
            outputs=[OutputType.COPY],
            options={"copy_style": "custom"},
        )


def test_copy_result_rejects_long_cta() -> None:
    """플랫폼 버튼에 들어가지 않는 긴 CTA는 저장 전에 거절합니다."""

    with pytest.raises(ValidationError):
        CopyResult(
            product_summary="수제 딸기잼",
            headline_candidates=["국산 딸기잼", "아침의 딸기잼", "수제 잼 만나기"],
            body_candidates=["상품 설명입니다."] * 3,
            cta_candidates=["지금 구매", "상품 보기", "간편한 아침을 시작하세요"],
            keywords=["딸기잼"],
        )


def test_request_requires_at_least_one_input() -> None:
    """텍스트와 이미지가 모두 없으면 생성할 근거가 없으므로 거절합니다."""

    with pytest.raises(ValidationError):
        GenerationRequest(
            request_id="empty_001",
            outputs=[OutputType.BANNER],
        )


def test_copy_output_requires_text() -> None:
    """이미지만 보고 임의의 상품 정보를 만들지 않도록 문구 생성에는 설명을 요구합니다."""

    with pytest.raises(ValidationError):
        GenerationRequest(
            request_id="image_copy_001",
            image_path="data/sample.jpg",
            outputs=[OutputType.COPY],
        )


def test_request_rejects_duplicate_outputs() -> None:
    """같은 파일을 두 번 생성하는 실수를 입력 단계에서 막습니다."""

    with pytest.raises(ValidationError):
        GenerationRequest(
            request_id="duplicate_001",
            text="수제 비누",
            outputs=[OutputType.BANNER, OutputType.BANNER],
        )


def test_request_rejects_invalid_id() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(
            request_id="한글 공백",
            text="테스트 상품",
            outputs=[OutputType.COPY],
        )


def test_bbox_rejects_reversed_coordinates() -> None:
    with pytest.raises(ValidationError):
        BoundingBox(xmin=20, ymin=20, xmax=10, ymax=100)
