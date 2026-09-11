"""승인 전에는 호출하지 않고, 승인 뒤 한 번만 실행하는 이미지 편집 작업."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from ad_service.api.schemas.detail_page import ProductImage
from ad_service.api.schemas.detail_page_store import StoredRevisionResult
from ad_service.api.schemas.generation import GenerationRequest
from ad_service.api.schemas.image_edit_job import (
    ApproveImageEditAttachmentRequest,
    ApproveImageEditJobRequest,
    CreateImageEditJobRequest,
    ImageEditAttachmentPreview,
    ImageEditJobResult,
)
from ad_service.core.budget import BudgetExceededError, BudgetLedger
from ad_service.factory import create_image_provider
from ad_service.models.image_generator import GPT_IMAGE_2_PRICES
from ad_service.pipelines.detail_page_store import (
    load_current_detail_page,
    save_prepared_detail_page_revision,
)
from ad_service.pipelines.revision import document_hash
from ad_service.prompts.templates import build_detail_page_image_edit_prompt
from ad_service.rendering.detail_page_html import render_detail_page_html

IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
RESULT_URL = re.compile(
    r"^/v1/results/(?P<request_id>[A-Za-z0-9_-]{1,80})/"
    r"(?P<filename>[A-Za-z0-9][A-Za-z0-9_.-]{0,199})$"
)
JOB_STORE_NAME = "detail-page-image-edits"
MAX_SOURCE_BYTES = 25 * 1024 * 1024
PROVIDER_MODELS = {"mock": "mock-image-v1", "gpt-image-2": "gpt-image-2"}


class ImageEditJobError(ValueError):
    pass


class ImageEditJobNotFound(ImageEditJobError):
    pass


class ImageEditJobConflict(ImageEditJobError):
    pass


class ImageEditJobUnsupported(ImageEditJobError):
    pass


class ImageEditJobExecutionError(RuntimeError):
    pass


def _canonical_bytes(value) -> bytes:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_root(output_root: Path) -> Path:
    base = output_root.expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    root = base / JOB_STORE_NAME
    if root.is_symlink():
        raise ImageEditJobConflict("이미지 편집 작업 저장소를 사용할 수 없습니다")
    root.mkdir(exist_ok=True)
    return root


def _job_dir(output_root: Path, job_id: str, *, required: bool = True) -> Path:
    if not IDENTIFIER.fullmatch(job_id):
        raise ImageEditJobNotFound("이미지 편집 작업을 찾을 수 없습니다")
    path = _job_root(output_root) / job_id
    if path.is_symlink():
        raise ImageEditJobNotFound("이미지 편집 작업을 찾을 수 없습니다")
    if required and not path.is_dir():
        raise ImageEditJobNotFound("이미지 편집 작업을 찾을 수 없습니다")
    return path


def _write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())


def _replace_json(path: Path, value: dict) -> None:
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        _write_new(temporary, _canonical_bytes(value))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_job(directory: Path) -> dict:
    path = directory / "job.json"
    if path.is_symlink() or not path.is_file():
        raise ImageEditJobConflict("이미지 편집 작업 파일을 읽을 수 없습니다")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ImageEditJobConflict("이미지 편집 작업 파일을 읽을 수 없습니다") from exc
    if not isinstance(value, dict):
        raise ImageEditJobConflict("이미지 편집 작업 정보가 잘못되었습니다")
    return value


@contextmanager
def _locked(directory: Path):
    lock_path = directory / ".write.lock"
    if lock_path.is_symlink():
        raise ImageEditJobConflict("이미지 편집 작업 잠금 파일을 사용할 수 없습니다")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@contextmanager
def _budget_locked(output_root: Path):
    path = output_root.expanduser().resolve() / ".image-edit-budget.lock"
    if path.is_symlink():
        raise ImageEditJobConflict("이미지 편집 예산 잠금 파일을 사용할 수 없습니다")
    with path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _managed_source_path(output_root: Path, asset_url: str) -> Path:
    match = RESULT_URL.fullmatch(asset_url)
    if not match:
        raise ImageEditJobUnsupported(
            "이미지 편집은 모델 서비스가 관리하는 /v1/results 자산만 지원합니다"
        )
    request_dir = (output_root.expanduser().resolve() / match["request_id"]).resolve()
    target = request_dir / match["filename"]
    if target.is_symlink() or not target.is_file():
        raise ImageEditJobUnsupported("편집할 원본 이미지 파일을 찾을 수 없습니다")
    resolved = target.resolve()
    if resolved.parent != request_dir:
        raise ImageEditJobUnsupported("편집할 원본 이미지 경로가 올바르지 않습니다")
    if resolved.stat().st_size > MAX_SOURCE_BYTES:
        raise ImageEditJobUnsupported("편집할 원본 이미지는 25MB 이하여야 합니다")
    return resolved


def _inspect_image(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise ImageEditJobUnsupported("지원되는 이미지 파일을 읽을 수 없습니다") from exc
    if width <= 0 or height <= 0 or width > 20000 or height > 20000:
        raise ImageEditJobUnsupported("원본 이미지 크기가 허용 범위를 벗어났습니다")
    return width, height


def _output_size(width: int, height: int) -> tuple[str, int, int]:
    ratio = width / height
    if ratio > 1.2:
        return "1536x1024", 1536, 1024
    if ratio < (1 / 1.2):
        return "1024x1536", 1024, 1536
    return "1024x1024", 1024, 1024


def _provider_quote(provider: str, quality: str, output_size: str) -> tuple[str, float]:
    if provider not in PROVIDER_MODELS:
        raise ImageEditJobUnsupported(f"{provider}는 승인형 이미지 편집을 지원하지 않습니다")
    if quality not in {"low", "medium", "high"}:
        raise ImageEditJobUnsupported("이미지 품질 설정이 올바르지 않습니다")
    if provider == "mock":
        return PROVIDER_MODELS[provider], 0.0
    try:
        return PROVIDER_MODELS[provider], GPT_IMAGE_2_PRICES[quality][output_size]
    except KeyError as exc:
        raise ImageEditJobUnsupported("이미지 편집 비용을 계산할 수 없습니다") from exc


def _find_image_block(document, block_id: str):
    for section in document.sections:
        for block in section.blocks:
            if block.content.block_id == block_id:
                if block.content.type != "image":
                    raise ImageEditJobConflict("이미지 블록만 이미지 편집을 요청할 수 있습니다")
                return block.content
    raise ImageEditJobConflict("편집할 이미지 블록을 찾을 수 없습니다")


def _approval_spec(job: dict) -> dict:
    keys = (
        "job_id",
        "document_id",
        "base_revision",
        "base_document_sha256",
        "block_id",
        "source_asset_id",
        "source_asset_url",
        "source_file_sha256",
        "instruction",
        "prompt",
        "provider",
        "model",
        "quality",
        "output_size",
        "width",
        "height",
        "seed",
        "estimated_cost_usd",
        "result_asset_id",
    )
    return {key: job[key] for key in keys}


def _public_result(job: dict, *, replayed: bool = False) -> ImageEditJobResult:
    public = {key: value for key, value in job.items() if not key.startswith("_")}
    public["replayed"] = replayed
    return ImageEditJobResult.model_validate(public)


def create_image_edit_job(
    document_id: str,
    request: CreateImageEditJobRequest,
    output_root: Path,
    provider: str,
    quality: str,
) -> ImageEditJobResult:
    """원본·버전·비용을 고정해 작업만 저장한다. 모델은 호출하지 않는다."""

    stored = load_current_detail_page(output_root, document_id)
    if (stored.document.revision, stored.document_sha256) != (
        request.base_revision,
        request.base_document_sha256,
    ):
        raise ImageEditJobConflict("문서가 변경되었습니다. 최신 문서로 다시 요청하세요")
    block = _find_image_block(stored.document, request.intent.block_id)
    if block.source_asset_id != request.intent.source_asset_id:
        raise ImageEditJobConflict("편집 의도의 원본 이미지가 현재 문서와 다릅니다")
    assets = {asset.asset_id: asset for asset in stored.document.assets}
    asset = assets.get(request.intent.source_asset_id)
    if asset is None:
        raise ImageEditJobConflict("편집할 이미지 자산이 문서에 없습니다")
    source_url = stored.asset_urls[asset.asset_id]
    source_path = _managed_source_path(output_root, source_url)
    source_width, source_height = _inspect_image(source_path)
    if (source_width, source_height) != (asset.width, asset.height):
        raise ImageEditJobConflict("원본 이미지 크기가 문서의 자산 정보와 다릅니다")

    output_size, width, height = _output_size(source_width, source_height)
    model, estimated_cost = _provider_quote(provider, quality, output_size)
    prompt = build_detail_page_image_edit_prompt(request.intent.instruction)
    created_at = _now()
    request_sha256 = _sha256_bytes(_canonical_bytes(request))
    asset_prefix = re.sub(r"[^A-Za-z0-9_-]", "_", asset.asset_id)[:55]
    asset_suffix = _sha256_bytes(
        f"{document_id}:{request.job_id}:{asset.asset_id}".encode("utf-8")
    )[:8]
    result_asset_id = f"{asset_prefix}_edit_{asset_suffix}"
    job = {
        "schema_version": "image-edit-job-0.1",
        "job_id": request.job_id,
        "status": "pending_approval",
        "document_id": document_id,
        "base_revision": request.base_revision,
        "base_document_sha256": request.base_document_sha256,
        "block_id": request.intent.block_id,
        "source_asset_id": request.intent.source_asset_id,
        "source_asset_url": source_url,
        "source_file_sha256": _sha256_file(source_path),
        "instruction": request.intent.instruction,
        "prompt": prompt,
        "provider": provider,
        "model": model,
        "quality": quality,
        "output_size": output_size,
        "width": width,
        "height": height,
        "seed": request.seed,
        "estimated_cost_usd": estimated_cost,
        "approval_sha256": "0" * 64,
        "approval_required": True,
        "approved_cost_cap_usd": None,
        "approval_operation_id": None,
        "recorded_cost_usd": None,
        "latency_ms": None,
        "result_asset_id": result_asset_id,
        "result_asset_url": None,
        "result_file_sha256": None,
        "attached_revision": None,
        "attachment_operation_id": None,
        "created_at": created_at,
        "approved_at": None,
        "finished_at": None,
        "attached_at": None,
        "error": None,
        "warnings": [
            "아직 이미지 모델을 호출하지 않았습니다. 표시된 사양과 비용을 승인해야 실행됩니다.",
            "생성형 편집은 상품 형태·로고·인쇄 문구를 바꿀 수 있어 결과 검수가 필요합니다.",
        ],
        "replayed": False,
        "persisted": True,
        "model_calls": 0,
        "image_generation_calls": 0,
        "_create_request_sha256": request_sha256,
        "_approval_request_sha256": None,
        "_attachment_request_sha256": None,
    }
    job["approval_sha256"] = _sha256_bytes(_canonical_bytes(_approval_spec(job)))

    root = _job_root(output_root)
    target = root / request.job_id
    if target.exists() or target.is_symlink():
        existing = _read_job(_job_dir(output_root, request.job_id))
        if existing.get("_create_request_sha256") == request_sha256:
            return _public_result(existing, replayed=True)
        raise ImageEditJobConflict("같은 job_id에 다른 이미지 편집 요청을 사용할 수 없습니다")
    staging = root / f".pending-{request.job_id}-{uuid4().hex}"
    staging.mkdir()
    try:
        _write_new(staging / "job.json", _canonical_bytes(job))
        try:
            os.replace(staging, target)
        except OSError as exc:
            raise ImageEditJobConflict("같은 ID의 이미지 편집 작업이 이미 있습니다") from exc
    finally:
        if staging.exists():
            staging.rmdir()
    return _public_result(job)


def load_image_edit_job(output_root: Path, job_id: str) -> ImageEditJobResult:
    return _public_result(_read_job(_job_dir(output_root, job_id)))


def _ensure_document_is_current(job: dict, output_root: Path) -> None:
    stored = load_current_detail_page(output_root, job["document_id"])
    if (stored.document.revision, stored.document_sha256) != (
        job["base_revision"],
        job["base_document_sha256"],
    ):
        raise ImageEditJobConflict("문서가 변경되어 이 이미지 편집 작업을 실행할 수 없습니다")
    block = _find_image_block(stored.document, job["block_id"])
    if block.source_asset_id != job["source_asset_id"]:
        raise ImageEditJobConflict("문서의 원본 이미지 참조가 변경되었습니다")


def approve_and_execute_image_edit_job(
    job_id: str,
    request: ApproveImageEditJobRequest,
    output_root: Path,
    service_budget_cap_usd: float,
) -> ImageEditJobResult:
    """승인 사양을 재검증하고 동기식으로 이미지 편집을 정확히 한 번 실행한다."""

    directory = _job_dir(output_root, job_id)
    approval_request_sha256 = _sha256_bytes(_canonical_bytes(request))
    with _locked(directory):
        job = _read_job(directory)
        if job.get("_approval_request_sha256") is not None:
            if job["_approval_request_sha256"] != approval_request_sha256:
                raise ImageEditJobConflict("이미 승인된 작업에 다른 승인 요청을 사용할 수 없습니다")
            return _public_result(job, replayed=True)
        if job["status"] != "pending_approval":
            raise ImageEditJobConflict("현재 상태에서는 이미지 편집 작업을 승인할 수 없습니다")
        if request.approval_sha256 != job["approval_sha256"]:
            raise ImageEditJobConflict("화면에서 승인한 이미지 편집 사양과 작업이 다릅니다")
        if request.approved_cost_cap_usd < job["estimated_cost_usd"]:
            raise ImageEditJobConflict("승인한 비용 상한이 예상 비용보다 낮습니다")

        _ensure_document_is_current(job, output_root)
        source_path = _managed_source_path(output_root, job["source_asset_url"])
        if _sha256_file(source_path) != job["source_file_sha256"]:
            raise ImageEditJobConflict("승인 전에 원본 이미지 파일이 변경되었습니다")

        job.update(
            {
                "status": "running",
                "approval_required": False,
                "approved_cost_cap_usd": request.approved_cost_cap_usd,
                "approval_operation_id": request.operation_id,
                "approved_at": _now(),
                "_approval_request_sha256": approval_request_sha256,
            }
        )
        _replace_json(directory / "job.json", job)

        try:
            provider = create_image_provider(job["provider"], job["quality"])
            if not provider.supports_reference_edit:
                raise ImageEditJobExecutionError("선택된 모델은 이미지 편집을 지원하지 않습니다")
            generation_request = GenerationRequest.model_validate(
                {
                    "request_id": job_id,
                    "text": job["instruction"],
                    "image_path": str(source_path),
                    "outputs": ["product_image"],
                    "options": {"image_input_strategy": "direct_edit"},
                }
            )
            with _budget_locked(output_root):
                ledger = BudgetLedger(output_root / "budget.json", service_budget_cap_usd)
                ledger.ensure_available(job["estimated_cost_usd"])
                job.update({"model_calls": 1, "image_generation_calls": 1})
                _replace_json(directory / "job.json", job)
                result = provider.edit_reference_image(
                    request=generation_request,
                    image_path=source_path,
                    asset_type="detail_page_image_edit",
                    width=job["width"],
                    height=job["height"],
                    prompt=job["prompt"],
                    seed=job["seed"],
                )
                ledger.record(result.metrics.estimated_cost_usd)

            edited_image = result.image.convert("RGB")
            if edited_image.size != (job["width"], job["height"]):
                raise ImageEditJobExecutionError(
                    "이미지 편집 결과 크기가 승인된 출력 사양과 다릅니다"
                )

            temporary = directory / f".result.{uuid4().hex}.png"
            try:
                edited_image.save(temporary, format="PNG")
                os.replace(temporary, directory / "result.png")
            finally:
                temporary.unlink(missing_ok=True)
        except Exception as exc:
            job.update(
                {
                    "status": "failed",
                    "finished_at": _now(),
                    "error": "이미지 편집 실행에 실패했습니다. 새 작업으로 다시 승인하세요.",
                }
            )
            _replace_json(directory / "job.json", job)
            if isinstance(exc, BudgetExceededError):
                raise
            if isinstance(exc, ImageEditJobExecutionError):
                raise
            raise ImageEditJobExecutionError("이미지 편집 모델을 실행하지 못했습니다") from exc

        job.update(
            {
                "status": "succeeded",
                "recorded_cost_usd": result.metrics.estimated_cost_usd,
                "latency_ms": result.metrics.latency_ms,
                "result_asset_url": f"/v1/detail-pages/image-edit-jobs/{job_id}/result",
                "result_file_sha256": _sha256_file(directory / "result.png"),
                "finished_at": _now(),
                "error": None,
            }
        )
        _replace_json(directory / "job.json", job)
        return _public_result(job)


def load_image_edit_result_path(output_root: Path, job_id: str) -> Path:
    directory = _job_dir(output_root, job_id)
    job = _read_job(directory)
    path = directory / "result.png"
    if job.get("status") != "succeeded" or path.is_symlink() or not path.is_file():
        raise ImageEditJobConflict("완료된 이미지 편집 결과가 없습니다")
    return path


def _prepare_attachment(
    job: dict,
    document,
    asset_urls: dict[str, str],
    output_root: Path,
):
    if job.get("status") != "succeeded":
        raise ImageEditJobConflict("성공한 이미지 편집 결과만 문서에 반영할 수 있습니다")
    if not job.get("result_asset_id") or not job.get("result_asset_url"):
        raise ImageEditJobConflict("이미지 편집 결과 자산 정보가 없습니다")
    if (document.revision, document_hash(document)) != (
        job["base_revision"],
        job["base_document_sha256"],
    ):
        raise ImageEditJobConflict("문서가 변경되어 편집 결과를 반영할 수 없습니다")

    result_path = load_image_edit_result_path(output_root, job["job_id"])
    result_sha256 = _sha256_file(result_path)
    if not job.get("result_file_sha256") or result_sha256 != job["result_file_sha256"]:
        raise ImageEditJobConflict("이미지 편집 결과 파일이 변경되었습니다")
    result_width, result_height = _inspect_image(result_path)
    if (result_width, result_height) != (job["width"], job["height"]):
        raise ImageEditJobConflict("이미지 편집 결과 크기가 작업 정보와 다릅니다")

    source_assets = {asset.asset_id: asset for asset in document.assets}
    source_asset = source_assets.get(job["source_asset_id"])
    if source_asset is None:
        raise ImageEditJobConflict("원본 이미지 자산이 현재 문서에 없습니다")
    if job["result_asset_id"] in source_assets:
        raise ImageEditJobConflict("편집 결과 자산 ID가 이미 문서에 있습니다")
    target = _find_image_block(document, job["block_id"])
    if target.source_asset_id != job["source_asset_id"]:
        raise ImageEditJobConflict("문서의 원본 이미지 참조가 변경되었습니다")

    document.assets.append(
        ProductImage(
            asset_id=job["result_asset_id"],
            role=source_asset.role,
            width=result_width,
            height=result_height,
        )
    )
    target.source_asset_id = job["result_asset_id"]
    document.revision += 1
    document = type(document).model_validate(document.model_dump(mode="json"))
    asset_urls[job["result_asset_id"]] = job["result_asset_url"]
    return document, asset_urls, result_sha256


def preview_image_edit_attachment(
    output_root: Path,
    job_id: str,
) -> ImageEditAttachmentPreview:
    """편집 결과를 새 자산으로 연결한 문서와 HTML을 저장 없이 만든다."""

    job = _read_job(_job_dir(output_root, job_id))
    stored = load_current_detail_page(output_root, job["document_id"])
    document, asset_urls, result_sha256 = _prepare_attachment(
        job,
        stored.document.model_copy(deep=True),
        dict(stored.asset_urls),
        output_root,
    )
    html = render_detail_page_html(document, asset_urls)
    return ImageEditAttachmentPreview(
        job_id=job_id,
        document=document,
        document_sha256=document_hash(document),
        html=html,
        html_sha256=_sha256_bytes(html.encode("utf-8")),
        result_asset_id=job["result_asset_id"],
        result_asset_url=job["result_asset_url"],
        result_file_sha256=result_sha256,
    )


def approve_image_edit_attachment(
    job_id: str,
    request: ApproveImageEditAttachmentRequest,
    output_root: Path,
) -> StoredRevisionResult:
    """검수한 편집 결과의 해시가 일치할 때만 새 문서 버전으로 저장한다."""

    directory = _job_dir(output_root, job_id)
    request_fingerprint = {
        "kind": "image_edit_attachment",
        "job_id": job_id,
        "approval": request.model_dump(mode="json"),
    }
    attachment_request_sha256 = _sha256_bytes(_canonical_bytes(request_fingerprint))
    with _locked(directory):
        job = _read_job(directory)
        existing_request = job.get("_attachment_request_sha256")
        if existing_request is not None and existing_request != attachment_request_sha256:
            raise ImageEditJobConflict(
                "이미 반영된 이미지 편집 작업에 다른 승인 요청을 사용할 수 없습니다"
            )
        if job.get("status") != "succeeded":
            raise ImageEditJobConflict("성공한 이미지 편집 결과만 문서에 반영할 수 있습니다")
        if request.approved_result_file_sha256 != job.get("result_file_sha256"):
            raise ImageEditJobConflict("사용자가 확인한 이미지 파일과 저장된 결과가 다릅니다")

        def build(document, asset_urls):
            prepared, prepared_urls, _ = _prepare_attachment(
                job,
                document,
                asset_urls,
                output_root,
            )
            return prepared, prepared_urls

        saved = save_prepared_detail_page_revision(
            job["document_id"],
            operation_id=request.operation_id,
            request_fingerprint=request_fingerprint,
            base_revision=job["base_revision"],
            base_document_sha256=job["base_document_sha256"],
            approved_document_sha256=request.approved_document_sha256,
            approved_html_sha256=request.approved_html_sha256,
            build=build,
            output_root=output_root,
            metadata_extra={
                "operation_kind": "image_edit_attachment",
                "source_image_edit_job_id": job_id,
                "source_result_file_sha256": job["result_file_sha256"],
            },
        )
        job.update(
            {
                "attached_revision": saved.revision,
                "attachment_operation_id": request.operation_id,
                "attached_at": _now(),
                "_attachment_request_sha256": attachment_request_sha256,
            }
        )
        _replace_json(directory / "job.json", job)
        return saved
