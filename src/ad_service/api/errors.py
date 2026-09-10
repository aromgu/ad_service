"""공통 에러 응답. `docs/api_spec.md` 섹션 1 의 엔벨로프로 통일한다."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class APIError(Exception):
    """라우터/파이프라인에서 던지는 도메인 에러. 핸들러가 엔벨로프로 변환한다."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []


# 자주 쓰는 것들.
class ValidationError(APIError):
    def __init__(self, message: str, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__("VALIDATION_ERROR", message, status_code=422, details=details)


class NotFoundError(APIError):
    def __init__(self, message: str) -> None:
        super().__init__("NOT_FOUND", message, status_code=404)


class PayloadTooLargeError(APIError):
    def __init__(self, message: str) -> None:
        super().__init__("PAYLOAD_TOO_LARGE", message, status_code=413)


class BudgetExceededError(APIError):
    def __init__(self, message: str) -> None:
        super().__init__("BUDGET_EXCEEDED", message, status_code=429)


class ModelUnavailableError(APIError):
    def __init__(self, message: str) -> None:
        super().__init__("MODEL_UNAVAILABLE", message, status_code=503)


def _envelope(code: str, message: str, details: list[dict[str, Any]] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "issue": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_envelope("VALIDATION_ERROR", "요청 형식이 올바르지 않습니다", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "BAD_REQUEST", 413: "PAYLOAD_TOO_LARGE"}.get(
            exc.status_code, "BAD_REQUEST" if exc.status_code < 500 else "INTERNAL_ERROR"
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=_envelope("INTERNAL_ERROR", "서버 내부 오류가 발생했습니다"),
        )
