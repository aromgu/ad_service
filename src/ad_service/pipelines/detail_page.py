"""사실을 그대로 구조화하는 mock. 파일·네트워크·모델 제공자를 사용하지 않는다."""

from ad_service.api.schemas.detail_page import (
    ContentReview,
    DetailPageRequest,
    DetailPageResult,
    DetailSection,
    ImageBlock,
    OmittedSection,
    SpecificationRow,
    TableBlock,
    TextBlock,
)


def generate_mock_detail_page(request: DetailPageRequest) -> DetailPageResult:
    product, options = request.product, request.content_request
    sections = []
    omitted = []
    warnings = [
        "mock 결과입니다. AI 문구·이미지 생성 및 상품 사실 검증을 실행하지 않았습니다.",
        "상품명과 제공된 사실을 그대로 사용했습니다. 표시 시 텍스트를 HTML로 해석하지 마세요.",
    ]
    if options.tone or options.target_audience or options.instruction:
        warnings.append("타깃·톤·추가 지시는 입력만 검증하며 mock 문구에 반영하지 않습니다.")
    if product.images:
        warnings.append(
            "사진은 참조 ID만 반환합니다. 자산 접근·존재 확인과 배경 처리는 실행하지 않습니다."
        )
        if options.image_strategy == "direct_edit":
            warnings.append("direct_edit 요청을 받았지만 실제 편집은 실행하지 않았습니다.")
    else:
        warnings.append("상품 사진이 없어 이미지 블록을 만들지 않았습니다.")
    if not product.facts:
        warnings.append("상품 사실이 없습니다. 규격·특징을 추가 확인하세요.")

    for kind in options.section_plan:
        section_id = f"sec_{kind}"
        if kind in ("features", "specifications") and not product.facts:
            omitted.append(
                OmittedSection(type=kind, reason="확인된 상품 사실이 없어 생략했습니다.")
            )
            continue
        blocks = []
        if kind == "hero":
            layout = "image_text" if options.primary_image_asset_id else "text_only"
            blocks.append(TextBlock(block_id="hero_heading", role="heading", text=product.name))
            if options.primary_image_asset_id:
                blocks.append(
                    ImageBlock(
                        block_id="hero_image",
                        source_asset_id=options.primary_image_asset_id,
                        alt=product.name,
                    )
                )
        elif kind == "features":
            layout = "feature_list"
            blocks.append(TextBlock(block_id="features_heading", role="heading", text="상품 특징"))
            for fact in product.facts:
                # 라벨은 별도 테이블에 보존; 값은 요약/확장 없이 그대로 전달한다.
                blocks.append(
                    TextBlock(
                        block_id=f"feature_{fact.fact_id}",
                        role="feature",
                        text=fact.value,
                        fact_refs=[fact.fact_id],
                    )
                )
        elif kind == "specifications":
            layout = "spec_table"
            blocks.append(
                TableBlock(
                    block_id="specifications_table",
                    rows=[
                        SpecificationRow(
                            label=fact.label, value=fact.value, fact_refs=[fact.fact_id]
                        )
                        for fact in product.facts
                    ],
                )
            )
        else:
            layout = "cta"
            blocks.append(TextBlock(block_id="cta_text", role="cta", text="상품 정보 확인하기"))
        sections.append(
            DetailSection(
                section_id=section_id,
                type=kind,
                layout=layout,
                blocks=blocks,
            )
        )

    return DetailPageResult(
        request_id=request.request_id,
        product_id=product.product_id,
        product_revision=product.revision,
        sections=sections,
        assets=[image.model_copy(deep=True) for image in product.images],
        review=ContentReview(
            missing_fields=list(product.missing_fields),
            omitted_sections=omitted,
            warnings=warnings,
        ),
    )
