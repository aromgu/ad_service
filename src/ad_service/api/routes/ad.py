from fastapi import APIRouter

from ad_service.schemas.ad import AdRequest, AdResponse

router = APIRouter()

@router.post("/generate", response_model=AdResponse)
def generate_ad(request: AdRequest):
    # TODO: 추후 실제 LLM 또는 AI 이미지 생성 모델 연동
    dummy_copy = f"[{request.category}] 트렌드를 이끄는 최고의 선택, {request.product_name}!"
    return AdResponse(
        status="success",
        message="광고 카피가 성공적으로 생성되었습니다.",
        generated_copy=dummy_copy
    )