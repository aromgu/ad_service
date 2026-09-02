from __future__ import annotations

import json

from ad_service.api.schemas.generation import (
    COPY_JSON_SCHEMA,
    AssetType,
    CampaignGoal,
    CopyLength,
    CopyStyle,
    GenerationRequest,
    ProductCategory,
    SalesChannel,
)

PRODUCT_CATEGORY_LABELS = {
    ProductCategory.SNACK_BEVERAGE: "간식·음료",
    ProductCategory.PACKAGED_FOOD: "가공·포장식품",
    ProductCategory.SIDE_DISH_MEAL: "반찬·간편식",
}
SALES_CHANNEL_LABELS = {
    SalesChannel.SMART_STORE: "스마트스토어",
    SalesChannel.SOCIAL_MEDIA: "SNS",
    SalesChannel.DELIVERY_APP: "배달앱",
    SalesChannel.OFFLINE_STORE: "오프라인 매장",
}
CAMPAIGN_GOAL_LABELS = {
    CampaignGoal.PRODUCT_LAUNCH: "신상품 소개",
    CampaignGoal.PROMOTION: "할인·이벤트 안내",
    CampaignGoal.BRAND_AWARENESS: "브랜드 홍보",
    CampaignGoal.PURCHASE_CONVERSION: "구매 유도",
}
COPY_STYLE_GUIDES = {
    CopyStyle.EMOTIONAL: "고객이 공감할 사용 장면을 담되 입력에 없는 상품 특성은 만들지 않는다.",
    CopyStyle.INFORMATIVE: "상품명과 확인된 특징을 먼저 전달하는 명확한 정보형 문장으로 쓴다.",
    CopyStyle.CONVERSION: (
        "구매 행동을 분명히 제안하되 입력에 없는 할인이나 긴급성을 만들지 않는다."
    ),
    CopyStyle.FRIENDLY: "동네 가게가 고객에게 설명하듯 자연스럽고 친근하게 쓴다.",
    CopyStyle.PREMIUM: "과장 없이 절제되고 차분한 어휘로 고급스러운 인상을 만든다.",
    CopyStyle.CUSTOM: "사용자의 추가 스타일 지시를 따르되 사실성과 출력 규칙을 우선한다.",
}
COPY_LENGTH_GUIDES = {
    CopyLength.SHORT: "헤드라인 8~16자, 본문 20~45자, CTA 2~8자",
    CopyLength.STANDARD: "헤드라인 12~25자, 본문 35~70자, CTA 2~8자",
    CopyLength.DETAILED: "헤드라인 12~25자, 본문 50~90자, CTA 2~8자",
}

COPY_INSTRUCTIONS = """
당신은 한국 소상공인 상품 광고 카피라이터다.
입력으로 제공된 사실만 사용하고 효능, 원산지, 친환경성, 사회적 가치처럼 확인되지 않은
주장을 추가하지 않는다. 자연스러운 한국어로 서로 다른 방향의 후보를 정확히 3개씩 만든다.
모든 글자 수는 공백과 문장부호를 포함해 계산한다.
헤드라인은 최대 25자, 본문은 최대 90자, CTA는 최대 8자를 절대 넘기지 않는다.
가격이나 혜택이 null이면 임의의 숫자, 할인율, 무료 혜택을 만들지 않는다.
입력에 없는 맛, 향, 품질, 효능, 인기도, 희소성도 사실처럼 추가하지 않는다.
""".strip()


def build_business_context(request: GenerationRequest) -> str:
    """선택 항목을 모델이 이해하기 쉬운 한글 문장으로 바꿉니다."""

    options = request.options
    parts = ["업종: 식료품 소매업"]
    if options.product_category is not None:
        parts.append(f"상품 카테고리: {PRODUCT_CATEGORY_LABELS[options.product_category]}")
    if options.sales_channel is not None:
        parts.append(f"판매 채널: {SALES_CHANNEL_LABELS[options.sales_channel]}")
    if options.campaign_goal is not None:
        parts.append(f"광고 목적: {CAMPAIGN_GOAL_LABELS[options.campaign_goal]}")
    return ", ".join(parts)


def build_copy_prompt(request: GenerationRequest) -> str:
    # 이미지 경로와 출력 파일 종류는 문구 내용에 도움이 되지 않으므로 모델에 보내지 않습니다.
    # 이렇게 하면 모델이 파일명을 상품 정보로 오해하는 것도 막을 수 있습니다.
    payload = request.model_dump(
        exclude={"image_path", "image_bbox", "outputs", "source"},
        mode="json",
    )
    preferences = request.options
    style_guide = COPY_STYLE_GUIDES[preferences.copy_style]
    length_guide = COPY_LENGTH_GUIDES[preferences.copy_length]
    must_include = ", ".join(preferences.must_include) or "없음"
    avoid_phrases = ", ".join(preferences.avoid_phrases) or "없음"
    custom_instruction = preferences.custom_instruction or "없음"
    emoji_rule = "허용" if preferences.use_emoji else "사용 금지"
    return (
        "다음 사용자 설명으로 광고 문구를 생성하세요. 입력에 없는 사실은 만들지 마세요.\n"
        f"광고 환경: {build_business_context(request)}\n"
        f"스타일 지침: {style_guide}\n"
        f"길이 지침: {length_guide}\n"
        f"이모지: {emoji_rule}\n"
        f"반드시 포함할 표현: {must_include}\n"
        f"사용하지 않을 표현: {avoid_phrases}\n"
        f"사용자 추가 요청: {custom_instruction}\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_qwen_copy_prompt(request: GenerationRequest) -> str:
    return (
        f"{COPY_INSTRUCTIONS}\n\n"
        f"JSON 스키마:\n{json.dumps(COPY_JSON_SCHEMA, ensure_ascii=False)}\n\n"
        f"요청:\n{build_copy_prompt(request)}\n\n"
        "JSON 객체만 출력하세요."
    )


def build_image_prompt(request: GenerationRequest, asset_type: AssetType) -> str:
    description = request.text or "the product shown in the reference image"
    tone = request.options.tone or "clean, trustworthy, modern"
    business_context = build_business_context(request)

    # 원본 이미지가 있으면 제품을 새로 그리지 않고 배경만 생성한 뒤 합성합니다.
    # 이미지가 없으면 설명을 바탕으로 완성된 제품 장면 전체를 생성합니다.
    if request.image_path:
        common = (
            "Create only a photorealistic advertising background. Do not draw the product, "
            "packaging, logo, letters, numbers, watermark, label, price, or CTA. "
            "The real product from the input image will be composited later. "
            f"Business context: {business_context}. User description: {description}. "
            f"Mood: {tone}. "
        )
    else:
        common = (
            "Create a photorealistic advertising visual based only on the user description. "
            "Do not add letters, numbers, watermark, logo, label, price, or CTA. "
            f"Business context: {business_context}. User description: {description}. "
            f"Mood: {tone}. "
        )
    if asset_type is AssetType.BANNER:
        return common + (
            "Landscape composition, keep the left 45 percent visually quiet for Korean copy, "
            "reserve the right side for the product, clean commercial lighting."
        )
    if asset_type is AssetType.DETAIL_VISUAL:
        return common + (
            "Portrait ecommerce detail-page hero, quiet top and lower areas for copy, "
            "center stage reserved for the product, coherent premium lighting."
        )
    return common + (
        "Square studio product-photo background, centered pedestal or surface, "
        "balanced soft shadow and uncluttered composition."
    )
