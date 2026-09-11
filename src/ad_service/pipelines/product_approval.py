"""사용자가 확인한 분석 후보만 공통 상품 사실로 승격한다."""

from ad_service.api.schemas.detail_page import (
    FactSource,
    ProductFact,
    ProductImage,
    ProductInput,
)
from ad_service.api.schemas.detail_page_plan import ProductApprovalRequest


def approve_product_analysis(request: ProductApprovalRequest) -> ProductInput:
    """분석 결과를 변경하지 않고 명시적으로 확정된 값만 ProductInput으로 만든다."""

    confirmed_fields = {item.field for item in request.confirmed_facts}
    returned_fields = {
        item.field
        for group in (
            request.analysis.candidates,
            request.analysis.unresolved,
            request.analysis.conflicts,
        )
        for item in group
    }
    missing_fields = sorted(returned_fields - confirmed_fields - {"name"})

    def reference(candidate_ids: list[str]) -> str:
        source = ",".join(candidate_ids) if candidate_ids else "manual"
        return f"seller-confirmed:{request.analysis.request_id}:{source}"

    facts = [
        ProductFact(
            fact_id=item.fact_id,
            label=item.label,
            value=item.value,
            source=FactSource(
                type="seller_input",
                reference=reference(item.source_candidate_ids),
            ),
        )
        for item in request.confirmed_facts
    ]
    images = [
        ProductImage(
            asset_id=asset.asset_id,
            role=(
                "primary_product"
                if asset.asset_id == request.primary_image_asset_id
                else "additional_product"
            ),
            width=asset.width,
            height=asset.height,
        )
        for asset in request.analysis.source_assets
        if asset.role == "product_image"
    ]
    return ProductInput(
        product_id=request.product_id,
        revision=request.revision,
        name=request.name,
        category_path=list(request.category_path),
        facts=facts,
        images=images,
        missing_fields=missing_fields,
    )
