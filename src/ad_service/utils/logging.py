"""loguru 기반 구조화 로깅.

- 개발: 사람이 읽기 쉬운 컬러 출력
- 운영(`AD_LOG_JSON=true`): 한 줄 JSON (로그 수집기용)

요청별 `request_id` 는 `logger.contextualize(request_id=...)` 로 바인딩한다
(observability.py 의 미들웨어).
"""

from __future__ import annotations

import sys

from loguru import logger

_configured = False


def configure_logging(level: str = "INFO", *, json_logs: bool = False) -> None:
    global _configured
    if _configured:
        return

    logger.remove()
    if json_logs:
        logger.add(sys.stdout, level=level, serialize=True, backtrace=False, diagnose=False)
    else:
        logger.add(
            sys.stdout,
            level=level,
            backtrace=False,
            diagnose=False,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{extra[request_id]}</cyan> | "
                "<level>{message}</level>"
            ),
        )
    logger.configure(extra={"request_id": "-"})
    _configured = True
