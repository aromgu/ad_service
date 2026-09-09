from typing import Any

__all__ = ["app", "create_app"]


def __getattr__(name: str) -> Any:
    """웹 앱을 실제로 요청할 때만 불러와 모델 모듈과의 순환 import를 막습니다."""

    if name in __all__:
        from ad_service.api.main import app, create_app

        return {"app": app, "create_app": create_app}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
