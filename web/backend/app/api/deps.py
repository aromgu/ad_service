from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.base import get_db
from app.db.models import User

DEMO_EMAIL = "demo@smith.local"
DEMO_NAME = "데모 사용자"

DbSession = Annotated[Session, Depends(get_db)]


def _get_or_create_demo_user(db: Session) -> User:
    user = db.query(User).filter(User.email == DEMO_EMAIL).one_or_none()
    if user is None:
        user = User(email=DEMO_EMAIL, name=DEMO_NAME, password_hash=None)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Bearer 토큰이 있으면 그 사용자, 없으면(개발 모드) 데모 계정.

    로그인 UI 가 붙기 전까지 생성 플로우를 막지 않기 위한 장치다.
    운영에서는 ALLOW_DEMO_USER=false 로 두고 토큰을 필수로 만든다.
    """
    if authorization and authorization.lower().startswith("bearer "):
        user_id = decode_access_token(authorization.split(" ", 1)[1].strip())
        if user_id:
            user = db.get(User, user_id)
            if user is not None:
                return user
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "유효하지 않은 토큰입니다.")

    if settings.allow_demo_user:
        return _get_or_create_demo_user(db)

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다.")


CurrentUser = Annotated[User, Depends(get_current_user)]
