from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from ad_service.core.config import get_settings

router = APIRouter(tags=["demo"])

# request_id는 GenerationRequest와 동일한 규칙을 사용합니다.
# 결과 파일 URL에 예상하지 못한 문자가 들어오는 것을 한 번 더 막는 역할도 합니다.
REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
DEMO_HTML_PATH = Path(__file__).resolve().parents[1] / "templates" / "demo.html"


@router.get("/demo", response_class=HTMLResponse, include_in_schema=False)
def demo_page() -> HTMLResponse:
    """모델 개발자가 브라우저에서 빠르게 시험할 수 있는 화면을 보여줍니다."""

    return HTMLResponse(DEMO_HTML_PATH.read_text(encoding="utf-8"))


@router.get("/v1/results/{request_id}/{filename}", include_in_schema=False)
def generated_result(request_id: str, filename: str) -> FileResponse:
    """생성된 이미지를 브라우저가 표시할 수 있도록 파일로 반환합니다.

    사용자가 파일 경로를 직접 조작해 다른 파일을 읽지 못하도록 요청 ID와 파일명을
    확인한 뒤, 설정된 결과 폴더 안에 있는 파일만 제공합니다.
    """

    if not REQUEST_ID_PATTERN.fullmatch(request_id):
        raise HTTPException(status_code=404, detail="result not found")
    if Path(filename).name != filename:
        raise HTTPException(status_code=404, detail="result not found")

    output_root = get_settings().output_root.resolve()
    request_dir = (output_root / request_id).resolve()
    target = (request_dir / filename).resolve()
    if target.parent != request_dir or not target.is_file():
        raise HTTPException(status_code=404, detail="result not found")

    return FileResponse(target)
