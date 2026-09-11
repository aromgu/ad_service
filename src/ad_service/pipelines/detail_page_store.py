"""상세페이지 승인본을 불변 버전으로 저장하는 로컬 파일 저장소."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from ad_service.api.schemas.detail_page_store import (
    ApproveRevisionRequest,
    RegisterDetailPageRequest,
    RevisionHistoryItem,
    RevisionHistoryResult,
    StoredDocumentResult,
    StoredRevisionResult,
)
from ad_service.api.schemas.revision import EditableDocument
from ad_service.pipelines.revision import document_hash, render_revision_preview
from ad_service.rendering.detail_page_html import render_detail_page_html

IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
STORE_NAME = "detail-pages"


class DetailPageStoreError(ValueError):
    pass


class DetailPageNotFound(DetailPageStoreError):
    pass


class DetailPageAlreadyExists(DetailPageStoreError):
    pass


class DetailPageConflict(DetailPageStoreError):
    pass


class DetailPageCorrupt(DetailPageStoreError):
    pass


def _canonical_bytes(value) -> bytes:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _store_root(output_root: Path) -> Path:
    base = output_root.expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    root = base / STORE_NAME
    if root.is_symlink():
        raise DetailPageCorrupt("상세페이지 저장소 심볼릭 링크는 사용할 수 없습니다")
    root.mkdir(exist_ok=True)
    return root


def _document_dir(output_root: Path, document_id: str, *, required: bool = True) -> Path:
    if not IDENTIFIER.fullmatch(document_id):
        raise DetailPageNotFound("상세페이지 문서를 찾을 수 없습니다")
    root = _store_root(output_root)
    directory = root / document_id
    if directory.is_symlink():
        raise DetailPageNotFound("상세페이지 문서를 찾을 수 없습니다")
    if required and not directory.is_dir():
        raise DetailPageNotFound("상세페이지 문서를 찾을 수 없습니다")
    return directory


def _revision_dir(directory: Path, revision: int) -> Path:
    if revision < 1:
        raise DetailPageNotFound("상세페이지 버전을 찾을 수 없습니다")
    path = directory / "revisions" / f"{revision:08d}"
    if path.is_symlink() or not path.is_dir():
        raise DetailPageNotFound("상세페이지 버전을 찾을 수 없습니다")
    return path


def _read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise DetailPageCorrupt("상세페이지 저장 파일을 읽을 수 없습니다")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DetailPageCorrupt("상세페이지 저장 파일을 읽을 수 없습니다") from exc


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


@contextmanager
def _locked(directory: Path):
    lock_path = directory / ".write.lock"
    if lock_path.is_symlink():
        raise DetailPageCorrupt("상세페이지 잠금 파일을 사용할 수 없습니다")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _urls(document_id: str, revision: int) -> tuple[str, str]:
    base = f"/v1/detail-pages/documents/{document_id}/revisions/{revision}"
    return f"{base}/document", f"{base}/html"


def _stored_result(metadata: dict, *, replayed: bool = False) -> StoredRevisionResult:
    document_url, html_url = _urls(metadata["document_id"], metadata["revision"])
    return StoredRevisionResult(
        document_id=metadata["document_id"],
        revision=metadata["revision"],
        document_sha256=metadata["document_sha256"],
        html_sha256=metadata["html_sha256"],
        operation_id=metadata["operation_id"],
        saved_at=metadata["saved_at"],
        replayed=replayed,
        document_url=document_url,
        html_url=html_url,
    )


def _write_revision(
    revisions: Path,
    document: EditableDocument,
    html: str,
    asset_urls: dict[str, str],
    metadata: dict,
) -> None:
    target = revisions / f"{document.revision:08d}"
    if target.exists() or target.is_symlink():
        raise DetailPageConflict("저장할 상세페이지 버전이 이미 존재합니다")
    staging = revisions / f".pending-{document.revision:08d}-{uuid4().hex}"
    staging.mkdir()
    try:
        _write_new(staging / "document.json", _canonical_bytes(document))
        _write_new(staging / "index.html", html.encode("utf-8"))
        _write_new(staging / "asset_urls.json", _canonical_bytes(asset_urls))
        _write_new(staging / "metadata.json", _canonical_bytes(metadata))
        os.replace(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _current(directory: Path) -> tuple[dict, EditableDocument, dict[str, str]]:
    pointer = _read_json(directory / "current.json")
    revision = pointer.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool):
        raise DetailPageCorrupt("현재 상세페이지 버전 정보가 잘못되었습니다")
    revision_path = _revision_dir(directory, revision)
    document = EditableDocument.model_validate(_read_json(revision_path / "document.json"))
    asset_urls = _read_json(revision_path / "asset_urls.json")
    if document.revision != revision or document_hash(document) != pointer.get("document_sha256"):
        raise DetailPageCorrupt("현재 상세페이지 버전과 문서가 일치하지 않습니다")
    if not isinstance(asset_urls, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in asset_urls.items()
    ):
        raise DetailPageCorrupt("상세페이지 자산 경로 정보가 잘못되었습니다")
    return pointer, document, asset_urls


def _metadata_for_operation(directory: Path, operation_id: str) -> dict | None:
    revisions = directory / "revisions"
    for path in sorted(revisions.iterdir(), reverse=True):
        if path.name.isdigit() and path.is_dir() and not path.is_symlink():
            metadata = _read_json(path / "metadata.json")
            if metadata.get("operation_id") == operation_id:
                return metadata
    return None


def register_detail_page(
    request: RegisterDetailPageRequest,
    output_root: Path,
) -> StoredRevisionResult:
    document = request.document.model_copy(deep=True)
    known_assets = {asset.asset_id for asset in document.assets}
    if set(request.asset_urls) != known_assets:
        raise DetailPageStoreError("문서 자산과 asset_urls 매핑이 정확히 일치해야 합니다")
    html = render_detail_page_html(document, request.asset_urls)
    document_sha256 = document_hash(document)
    html_sha256 = _sha256(html.encode("utf-8"))
    request_sha256 = _sha256(_canonical_bytes(request))
    saved_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "document_id": document.document_id,
        "revision": document.revision,
        "document_sha256": document_sha256,
        "html_sha256": html_sha256,
        "operation_id": request.operation_id,
        "request_sha256": request_sha256,
        "saved_at": saved_at,
        "base_revision": None,
    }
    root = _store_root(output_root)
    target = root / document.document_id
    if target.exists() or target.is_symlink():
        try:
            existing = _metadata_for_operation(target, request.operation_id)
        except (OSError, DetailPageStoreError):
            existing = None
        if existing and existing.get("request_sha256") == request_sha256:
            return _stored_result(existing, replayed=True)
        raise DetailPageAlreadyExists("같은 ID의 상세페이지 문서가 이미 있습니다")
    staging = root / f".pending-{document.document_id}-{uuid4().hex}"
    staging.mkdir()
    try:
        revisions = staging / "revisions"
        revisions.mkdir()
        _write_revision(revisions, document, html, request.asset_urls, metadata)
        _replace_json(staging / "current.json", metadata)
        try:
            os.replace(staging, target)
        except OSError as exc:
            raise DetailPageAlreadyExists("같은 ID의 상세페이지 문서가 이미 있습니다") from exc
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return _stored_result(metadata)


def approve_detail_page_revision(
    document_id: str,
    request: ApproveRevisionRequest,
    output_root: Path,
) -> StoredRevisionResult:
    directory = _document_dir(output_root, document_id)
    request_sha256 = _sha256(_canonical_bytes(request))
    with _locked(directory):
        pointer, document, asset_urls = _current(directory)
        existing = _metadata_for_operation(directory, request.operation_id)
        if existing:
            if existing.get("request_sha256") != request_sha256:
                raise DetailPageConflict("같은 operation_id에 다른 승인 요청을 사용할 수 없습니다")
            if existing["revision"] > pointer["revision"]:
                _replace_json(directory / "current.json", existing)
            return _stored_result(existing, replayed=True)

        rendered = render_revision_preview(document, request.proposal, asset_urls)
        if rendered.preview.status != "needs_review":
            raise DetailPageConflict("확인 질문이 남은 수정안은 승인할 수 없습니다")
        if rendered.preview.image_edit_intents:
            raise DetailPageConflict("완료되지 않은 이미지 편집 작업이 있어 승인할 수 없습니다")
        if not rendered.preview.changes:
            raise DetailPageConflict("실제로 변경된 내용이 없습니다")
        if (
            rendered.preview.document_sha256 != request.approved_document_sha256
            or rendered.html_sha256 != request.approved_html_sha256
        ):
            raise DetailPageConflict("승인한 미리보기와 현재 렌더링 결과가 일치하지 않습니다")
        if rendered.preview.document.revision != document.revision + 1:
            raise DetailPageConflict("상세페이지 버전 증가가 올바르지 않습니다")

        saved_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "document_id": document_id,
            "revision": rendered.preview.document.revision,
            "document_sha256": rendered.preview.document_sha256,
            "html_sha256": rendered.html_sha256,
            "operation_id": request.operation_id,
            "request_sha256": request_sha256,
            "saved_at": saved_at,
            "base_revision": document.revision,
        }
        _write_revision(
            directory / "revisions",
            rendered.preview.document,
            rendered.html,
            asset_urls,
            metadata,
        )
        # 불변 버전 파일을 모두 쓴 뒤 현재 포인터를 마지막에 교체한다.
        _replace_json(directory / "current.json", metadata)
        return _stored_result(metadata)


def save_prepared_detail_page_revision(
    document_id: str,
    *,
    operation_id: str,
    request_fingerprint: dict,
    base_revision: int,
    base_document_sha256: str,
    approved_document_sha256: str,
    approved_html_sha256: str,
    build: Callable[
        [EditableDocument, dict[str, str]],
        tuple[EditableDocument, dict[str, str]],
    ],
    output_root: Path,
    metadata_extra: dict[str, object] | None = None,
) -> StoredRevisionResult:
    """서버가 준비한 문서를 승인 해시와 대조해 새 불변 버전으로 저장한다.

    자연어 수정안이 아닌 서버 내부 작업 결과를 붙일 때 사용한다. 클라이언트가 보낸 문서를
    저장하지 않고, 잠금 안에서 최신 문서를 다시 읽은 뒤 ``build``로 결과를 재구성한다.
    """

    directory = _document_dir(output_root, document_id)
    request_sha256 = _sha256(_canonical_bytes(request_fingerprint))
    with _locked(directory):
        pointer, document, asset_urls = _current(directory)
        existing = _metadata_for_operation(directory, operation_id)
        if existing:
            if existing.get("request_sha256") != request_sha256:
                raise DetailPageConflict("같은 operation_id에 다른 승인 요청을 사용할 수 없습니다")
            if existing["revision"] > pointer["revision"]:
                _replace_json(directory / "current.json", existing)
            return _stored_result(existing, replayed=True)

        if (document.revision, pointer["document_sha256"]) != (
            base_revision,
            base_document_sha256,
        ):
            raise DetailPageConflict("문서가 변경되었습니다. 최신 문서로 다시 확인하세요")

        prepared, prepared_asset_urls = build(
            document.model_copy(deep=True),
            dict(asset_urls),
        )
        prepared = EditableDocument.model_validate(prepared.model_dump(mode="json"))
        if prepared.document_id != document_id:
            raise DetailPageConflict("준비된 상세페이지 문서 ID가 다릅니다")
        if prepared.revision != document.revision + 1:
            raise DetailPageConflict("상세페이지 버전 증가가 올바르지 않습니다")
        known_assets = {asset.asset_id for asset in prepared.assets}
        if set(prepared_asset_urls) != known_assets:
            raise DetailPageConflict("문서 자산과 asset_urls 매핑이 정확히 일치해야 합니다")

        html = render_detail_page_html(prepared, prepared_asset_urls)
        document_sha256 = document_hash(prepared)
        html_sha256 = _sha256(html.encode("utf-8"))
        if document_sha256 != approved_document_sha256 or html_sha256 != approved_html_sha256:
            raise DetailPageConflict("승인한 미리보기와 현재 렌더링 결과가 일치하지 않습니다")

        saved_at = datetime.now(timezone.utc).isoformat()
        metadata: dict[str, object] = {
            "document_id": document_id,
            "revision": prepared.revision,
            "document_sha256": document_sha256,
            "html_sha256": html_sha256,
            "operation_id": operation_id,
            "request_sha256": request_sha256,
            "saved_at": saved_at,
            "base_revision": document.revision,
        }
        if metadata_extra:
            overlap = set(metadata) & set(metadata_extra)
            if overlap:
                raise DetailPageConflict("추가 메타데이터가 저장 필드를 덮어쓸 수 없습니다")
            metadata.update(metadata_extra)
        _write_revision(
            directory / "revisions",
            prepared,
            html,
            prepared_asset_urls,
            metadata,
        )
        _replace_json(directory / "current.json", metadata)
        return _stored_result(metadata)


def load_current_detail_page(output_root: Path, document_id: str) -> StoredDocumentResult:
    directory = _document_dir(output_root, document_id)
    pointer, document, asset_urls = _current(directory)
    document_url, html_url = _urls(document_id, document.revision)
    return StoredDocumentResult(
        document=document,
        document_sha256=pointer["document_sha256"],
        html_sha256=pointer["html_sha256"],
        asset_urls=asset_urls,
        saved_at=pointer["saved_at"],
        document_url=document_url,
        html_url=html_url,
    )


def list_detail_page_revisions(output_root: Path, document_id: str) -> RevisionHistoryResult:
    directory = _document_dir(output_root, document_id)
    pointer, _, _ = _current(directory)
    items = []
    for path in sorted((directory / "revisions").iterdir(), reverse=True):
        if path.name.isdigit() and path.is_dir() and not path.is_symlink():
            metadata = _read_json(path / "metadata.json")
            items.append(
                RevisionHistoryItem(
                    document_id=metadata["document_id"],
                    revision=metadata["revision"],
                    document_sha256=metadata["document_sha256"],
                    html_sha256=metadata["html_sha256"],
                    operation_id=metadata["operation_id"],
                    saved_at=metadata["saved_at"],
                    base_revision=metadata.get("base_revision"),
                )
            )
    return RevisionHistoryResult(
        document_id=document_id,
        current_revision=pointer["revision"],
        items=items,
    )


def load_detail_page_revision_document(
    output_root: Path,
    document_id: str,
    revision: int,
) -> EditableDocument:
    directory = _document_dir(output_root, document_id)
    return EditableDocument.model_validate(
        _read_json(_revision_dir(directory, revision) / "document.json")
    )


def load_detail_page_revision_html(
    output_root: Path,
    document_id: str,
    revision: int,
) -> str:
    directory = _document_dir(output_root, document_id)
    path = _revision_dir(directory, revision) / "index.html"
    if path.is_symlink() or not path.is_file():
        raise DetailPageCorrupt("상세페이지 HTML을 읽을 수 없습니다")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DetailPageCorrupt("상세페이지 HTML을 읽을 수 없습니다") from exc
