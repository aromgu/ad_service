from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import ShippingSettings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/shipping", response_model=ShippingSettings)
def get_shipping(user: CurrentUser) -> ShippingSettings:
    """저장된 배송 설정. 4a 폼의 초기값으로 쓰인다."""
    return ShippingSettings(**(user.shipping_settings or {}))


@router.put("/shipping", response_model=ShippingSettings)
def put_shipping(payload: ShippingSettings, user: CurrentUser, db: DbSession) -> ShippingSettings:
    """한 번 저장하면 다음 등록에도 그대로 쓰인다."""
    user.shipping_settings = payload.model_dump()
    db.commit()
    return payload
