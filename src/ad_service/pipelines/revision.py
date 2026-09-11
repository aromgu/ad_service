"""수정안의 순수 미리보기. 원본 변경·모델 호출·파일 접근 없이 전체 성공/실패한다."""

import hashlib
import json

from ad_service.api.schemas.revision import (
    EditableDocument,
    ImageEditIntent,
    RevisionPreviewResult,
    RevisionProposal,
    RevisionRenderResult,
    summarize_changes,
)
from ad_service.rendering.detail_page_html import render_detail_page_html


class RevisionConflict(ValueError):
    pass


def document_hash(document: EditableDocument) -> str:
    canonical = json.dumps(
        document.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def preview_revision(
    document: EditableDocument, proposal: RevisionProposal
) -> RevisionPreviewResult:
    if (proposal.base_revision, proposal.base_sha256) != (
        document.revision,
        document_hash(document),
    ):
        raise RevisionConflict("문서가 변경되었습니다. 최신 문서로 수정안을 다시 확인하세요")
    draft = document.model_copy(deep=True)
    if proposal.decision == "needs_clarification":
        return RevisionPreviewResult(
            status="needs_clarification",
            document=draft,
            document_sha256=document_hash(draft),
            reply=proposal.reply,
            footer=summarize_changes([]),
            question=proposal.question,
        )

    def section(section_id):
        for item in draft.sections:
            if item.section_id == section_id:
                return item
        raise ValueError(f"없는 섹션: {section_id}")

    def block(block_id):
        for parent in draft.sections:
            for item in parent.blocks:
                if item.content.block_id == block_id:
                    return parent, item
        raise ValueError(f"없는 블록: {block_id}")

    def insert(items, index, item):
        if index > len(items):
            raise ValueError("삽입 위치가 범위를 벗어났습니다")
        items.insert(index, item)

    changes, intents = [], []
    for operation in proposal.operations:
        before = draft.model_dump(mode="json")
        op = operation.op
        if hasattr(operation, "block_id"):
            parent, target = block(operation.block_id)
            content = target.content
        if op == "replace_text":
            if content.type != "text":
                raise ValueError("텍스트 블록만 문구를 수정할 수 있습니다")
            content.text = operation.text
            content.fact_refs = list(operation.fact_refs)
        elif op == "replace_image":
            if content.type != "image":
                raise ValueError("이미지 블록이 아닙니다")
            content.source_asset_id = operation.asset_id
            content.alt = operation.alt
        elif op == "edit_image":
            if content.type != "image":
                raise ValueError("이미지 블록이 아닙니다")
            if any(i.block_id == content.block_id for i in intents):
                raise ValueError("한 이미지에 중복 편집 작업을 요청할 수 없습니다")
            intents.append(
                ImageEditIntent(
                    block_id=content.block_id,
                    source_asset_id=content.source_asset_id,
                    instruction=operation.instruction,
                )
            )
        elif op == "set_style":
            updates = operation.model_dump(exclude_none=True, exclude={"op", "block_id"})
            target.style = target.style.model_copy(update=updates)
        elif op == "replace_table":
            if content.type != "table":
                raise ValueError("표 블록이 아닙니다")
            content.rows = [row.model_copy(deep=True) for row in operation.rows]
        elif op == "remove_block":
            parent.blocks.remove(target)
        elif op == "move_block":
            destination = section(operation.section_id)
            parent.blocks.remove(target)
            insert(destination.blocks, operation.index, target)
        elif op == "add_block":
            insert(
                section(operation.section_id).blocks,
                operation.index,
                operation.block.model_copy(deep=True),
            )
        elif op == "set_layout":
            section(operation.section_id).layout = operation.layout
        elif op == "remove_section":
            draft.sections.remove(section(operation.section_id))
        elif op == "move_section":
            target_section = section(operation.section_id)
            draft.sections.remove(target_section)
            insert(draft.sections, operation.index, target_section)
        elif op == "add_section":
            insert(draft.sections, operation.index, operation.section.model_copy(deep=True))
        else:
            raise ValueError("지원하지 않는 작업")
        # 각 작업 뒤에도 ID·참조·문서 구조가 유효해야 한다.
        draft = EditableDocument.model_validate(draft.model_dump(mode="json"))
        if before != draft.model_dump(mode="json"):
            changes.append(operation.model_dump(mode="json"))

    # 이미지 작업을 만든 뒤 같은 배치에서 원본을 바꾸거나 삭제하는 모순은 거부한다.
    for intent in intents:
        _, target = block(intent.block_id)
        if (
            target.content.type != "image"
            or target.content.source_asset_id != intent.source_asset_id
        ):
            raise ValueError("편집할 이미지가 다른 수정 작업에서 변경되었습니다")
    if changes:
        draft.revision += 1
    return RevisionPreviewResult(
        status="needs_review",
        document=draft,
        document_sha256=document_hash(draft),
        reply=proposal.reply,
        footer=summarize_changes(changes),
        changes=changes,
        image_edit_intents=intents,
        warnings=[
            "수정안 미리보기입니다. 자연어 해석·이미지 생성·영구 저장은 실행하지 않았습니다.",
            "사실 참조의 존재는 검사하지만 문구의 사실성은 판매자 검토가 필요합니다.",
            "이미지는 참조만 검사합니다. 실제 자산의 존재·접근 권한은 저장 전에 확인하세요.",
        ],
    )


def render_revision_preview(
    document: EditableDocument,
    proposal: RevisionProposal,
    asset_urls: dict[str, str],
) -> RevisionRenderResult:
    """수정안을 다시 검증하고 저장 없이 브라우저용 HTML을 만든다."""

    preview = preview_revision(document, proposal)
    if preview.status == "needs_clarification":
        return RevisionRenderResult(preview=preview, html=None, html_sha256=None)
    known_assets = {asset.asset_id for asset in preview.document.assets}
    if set(asset_urls) != known_assets:
        raise ValueError("문서 자산과 asset_urls 매핑이 정확히 일치해야 합니다")
    rendered = render_detail_page_html(preview.document, asset_urls)
    return RevisionRenderResult(
        preview=preview,
        html=rendered,
        html_sha256=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    )
