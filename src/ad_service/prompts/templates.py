from __future__ import annotations

import json

from ad_service.api.schemas.generation import COPY_JSON_SCHEMA, AssetType, GenerationRequest

COPY_INSTRUCTIONS = """
당신은 한국 소상공인 상품 광고 카피라이터다.
입력으로 제공된 사실만 사용하고 효능, 원산지, 친환경성, 사회적 가치처럼 확인되지 않은
주장을 추가하지 않는다. 자연스러운 한국어로 서로 다른 방향의 후보를 정확히 3개씩 만든다.
헤드라인은 24자 이내, 본문은 70자 이내, CTA는 12자 이내로 작성한다.
가격이나 혜택이 null이면 임의의 숫자, 할인율, 무료 혜택을 만들지 않는다.
""".strip()


def build_copy_prompt(request: GenerationRequest) -> str:
    payload = request.model_dump(
        exclude={"product_image_path", "product_bbox", "source"},
        mode="json",
    )
    return (
        "다음 상품 정보로 광고 문구를 생성하세요. 입력에 없는 사실은 만들지 마세요.\n"
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
    feature_text = ", ".join(request.features)
    common = (
        "Create only a photorealistic advertising background. Do not draw the product, "
        "packaging, logo, letters, numbers, watermark, label, price, or CTA. "
        f"The real product will be composited later. Category: {request.category}. "
        f"Product cues: {feature_text}. Mood: {request.tone}. "
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
