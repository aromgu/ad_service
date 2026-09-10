"""관측성 배선: /metrics, request_id 상관관계, 요청 로깅."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """요청마다 request_id 를 만들어 로그 컨텍스트에 바인딩하고 응답 헤더로 돌려준다."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        with logger.contextualize(request_id=request_id):
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("unhandled error {} {}", request.method, request.url.path)
                raise
            elapsed_ms = (time.perf_counter() - started) * 1000
            # 헬스체크/메트릭 폴링은 시끄러우니 debug 로
            level = "DEBUG" if request.url.path in ("/health", "/metrics") else "INFO"
            logger.log(
                level,
                "{} {} {} {:.0f}ms",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def setup_observability(app: FastAPI) -> None:
    app.add_middleware(RequestContextMiddleware)
    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/metrics", "/health"],
    ).instrument(app).expose(app, include_in_schema=False)
