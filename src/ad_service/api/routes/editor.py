from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

from ad_service.api.schemas.editor import EditorScene
from ad_service.api.schemas.generation import AssetType, GenerationResult
from ad_service.core.config import get_settings
from ad_service.pipelines.editing import default_scene, load_layers, render_scene, saved_scene

router = APIRouter(tags=["editor"])
IDENTIFIER = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


def run_directory(request_id: str) -> Path:
    root = get_settings().output_root.resolve()
    directory = (root / request_id).resolve()
    if not IDENTIFIER.fullmatch(request_id) or directory.parent != root or not directory.is_dir():
        raise HTTPException(404, "생성 결과를 찾을 수 없습니다.")
    return directory


def layers(request_id: str, kind: AssetType):
    try:
        return load_layers(run_directory(request_id), kind)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "결과 파일을 읽을 수 없습니다.") from exc


def revision_file(request_id: str, kind: AssetType, revision: str, suffix: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", revision):
        raise HTTPException(404, "수정본을 찾을 수 없습니다.")
    run = run_directory(request_id)
    edits = run / "edits"
    if edits.is_symlink():
        raise HTTPException(404, "수정본 폴더를 사용할 수 없습니다.")
    path = edits / f"{kind.value}_{revision}.{suffix}"
    if path.is_symlink():
        raise HTTPException(404, "수정본을 찾을 수 없습니다.")
    return path


@router.get("/demo/editor", response_class=HTMLResponse, include_in_schema=False)
def editor_page():
    path = Path(__file__).resolve().parents[1] / "templates" / "editor.html"
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/v1/editor/jobs")
def editor_jobs():
    root = get_settings().output_root.resolve()
    if not root.is_dir():
        return {"items": []}
    items = []
    for folder in root.iterdir():
        if folder.is_symlink() or not folder.is_dir() or not IDENTIFIER.fullmatch(folder.name):
            continue
        file = folder / "result.json"
        if file.is_symlink() or not file.is_file():
            continue
        try:
            result = GenerationResult.model_validate_json(file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if result.assets:
            items.append(
                {
                    "request_id": folder.name,
                    "title": result.copy_result.product_summary
                    if result.copy_result
                    else folder.name,
                    "assets": [asset.type.value for asset in result.assets],
                    "updated_at": file.stat().st_mtime,
                }
            )
    return {"items": sorted(items, key=lambda item: item["updated_at"], reverse=True)[:50]}


@router.get("/v1/editor/{request_id}/{kind}")
def editor_document(request_id: str, kind: AssetType, revision: str | None = None):
    result, asset, background, cutout = layers(request_id, kind)
    scene = default_scene(result, kind, background, cutout)
    revisions = []
    edits = run_directory(request_id) / "edits"
    if edits.is_dir() and not edits.is_symlink():
        for file in sorted(
            edits.glob(f"{kind.value}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:50]:
            token = file.stem.removeprefix(f"{kind.value}_")
            if re.fullmatch(r"[a-f0-9]{32}", token) and not file.is_symlink():
                revisions.append({"id": token, "saved_at": file.stat().st_mtime})
    if revision:
        file = revision_file(request_id, kind, revision, "json")
        if not file.is_file():
            raise HTTPException(404, "수정본을 찾을 수 없습니다.")
        try:
            scene = saved_scene(file)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, "수정본을 읽을 수 없습니다.") from exc
    return {
        "request_id": request_id,
        "asset": kind.value,
        "width": background.width,
        "height": background.height,
        "product_editable": cutout is not None,
        "product_size": list(cutout.size) if cutout else None,
        "copy_candidates": result.copy_result.model_dump() if result.copy_result else None,
        "scene": scene.model_dump(),
        "revisions": revisions,
        "original_url": f"/v1/results/{request_id}/{kind.value}.png",
        "model": asset.model,
    }


def png_bytes(request_id: str, kind: AssetType, scene: EditorScene) -> bytes:
    _, _, background, cutout = layers(request_id, kind)
    try:
        image = render_scene(background, cutout, scene)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@router.post("/v1/editor/{request_id}/{kind}/preview")
def preview(request_id: str, kind: AssetType, scene: EditorScene):
    return Response(
        png_bytes(request_id, kind, scene),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/v1/editor/{request_id}/{kind}/save", status_code=201)
def save_revision(request_id: str, kind: AssetType, scene: EditorScene):
    image = png_bytes(request_id, kind, scene)
    revision = uuid4().hex
    metadata = revision_file(request_id, kind, revision, "json")
    image_path = revision_file(request_id, kind, revision, "png")
    metadata.parent.mkdir(exist_ok=True)
    # 기존 원본은 바꾸지 않고 고유 ID로 수정본·설정을 함께 저장합니다.
    image_path.write_bytes(image)
    with metadata.open("x", encoding="utf-8") as file:
        json.dump(
            {
                "request_id": request_id,
                "asset": kind.value,
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "scene": scene.model_dump(),
                "model_calls": 0,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
    return {
        "revision": revision,
        "download_url": f"/v1/editor/{request_id}/{kind.value}/revisions/{revision}/image",
    }


@router.get("/v1/editor/{request_id}/{kind}/revisions/{revision}/image")
def download_revision(request_id: str, kind: AssetType, revision: str):
    path = revision_file(request_id, kind, revision, "png")
    if not path.is_file():
        raise HTTPException(404, "수정본을 찾을 수 없습니다.")
    return FileResponse(
        path, media_type="image/png", filename=f"{request_id}_{kind.value}_{revision[:8]}.png"
    )
