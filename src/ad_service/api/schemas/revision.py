"""UI 독립적인 수정안 계약. 자연어 해석/영구 저장/유료 실행과 분리한다."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from ad_service.api.schemas.detail_page import (
    BlockIdentifier,
    ContentBlock,
    ContractModel,
    FactText,
    Identifier,
    ProductFact,
    ProductImage,
    SpecificationRow,
)

Color = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
SafeSameOriginAssetUrl = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=500,
        pattern=r"^/?[A-Za-z0-9][A-Za-z0-9_./-]*$",
    ),
]


class BlockStyle(ContractModel):
    color: Color = "#222222"
    background_color: Color = "#ffffff"
    font_size: int = Field(default=24, ge=10, le=120, strict=True)
    align: Literal["left", "center", "right"] = "left"
    width_percent: int = Field(default=100, ge=10, le=100, strict=True)


class EditableBlock(ContractModel):
    content: ContentBlock
    style: BlockStyle = Field(default_factory=BlockStyle)


class EditableSection(ContractModel):
    section_id: Identifier
    kind: Literal["hero", "story", "features", "specifications", "cta", "custom"]
    layout: Literal["stack", "image_left", "image_right", "grid"] = "stack"
    blocks: list[EditableBlock] = Field(min_length=1, max_length=60)


class EditableDocument(ContractModel):
    schema_version: Literal["revision-0.1"] = "revision-0.1"
    document_id: Identifier
    revision: int = Field(ge=1, strict=True)
    sections: list[EditableSection] = Field(min_length=1, max_length=30)
    assets: list[ProductImage] = Field(default_factory=list, max_length=50)
    facts: list[ProductFact] = Field(default_factory=list, max_length=100)
    missing_fields: list[FactText] = Field(default_factory=list, max_length=50)
    review_notes: list[FactText] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def references_are_valid(self):
        blocks = [b.content for s in self.sections for b in s.blocks]
        for ids in (
            [s.section_id for s in self.sections],
            [b.block_id for b in blocks],
            [a.asset_id for a in self.assets],
            [f.fact_id for f in self.facts],
        ):
            if len(ids) != len(set(ids)):
                raise ValueError("섹션·블록·자산·사실 ID는 각각 고유해야 합니다")
        assets = {a.asset_id for a in self.assets}
        facts = {f.fact_id: f for f in self.facts}
        for block in blocks:
            if block.type == "image" and block.source_asset_id not in assets:
                raise ValueError("등록되지 않은 이미지 참조")
            if block.type == "text" and not set(block.fact_refs) <= facts.keys():
                raise ValueError("등록되지 않은 사실 참조")
            if block.type == "table":
                for row in block.rows:
                    if not set(row.fact_refs) <= facts.keys():
                        raise ValueError("표에 등록되지 않은 사실 참조")
                    if not any(
                        (row.label, row.value) == (facts[ref].label, facts[ref].value)
                        for ref in row.fact_refs
                    ):
                        raise ValueError("정보 표에는 제공된 사실의 라벨과 값을 그대로 사용하세요")
        return self


class BlockTarget(ContractModel):
    block_id: BlockIdentifier


class ReplaceText(BlockTarget):
    op: Literal["replace_text"]
    text: FactText
    fact_refs: list[Identifier] = Field(default_factory=list, max_length=50)


class ReplaceImage(BlockTarget):
    op: Literal["replace_image"]
    asset_id: Identifier
    alt: FactText


class EditImage(BlockTarget):
    op: Literal["edit_image"]
    instruction: FactText


class SetStyle(BlockTarget):
    op: Literal["set_style"]
    # 지정한 항목만 변경한다. 임의 CSS / HTML은 받지 않는다.
    color: Color | None = None
    background_color: Color | None = None
    font_size: int | None = Field(default=None, ge=10, le=120, strict=True)
    align: Literal["left", "center", "right"] | None = None
    width_percent: int | None = Field(default=None, ge=10, le=100, strict=True)

    @model_validator(mode="after")
    def nonempty_style(self):
        if not self.model_dump(exclude_none=True, exclude={"op", "block_id"}):
            raise ValueError("수정할 스타일 항목이 없습니다")
        return self


class ReplaceTable(BlockTarget):
    op: Literal["replace_table"]
    rows: list[SpecificationRow] = Field(min_length=1, max_length=50)


class RemoveBlock(BlockTarget):
    op: Literal["remove_block"]


class MoveBlock(BlockTarget):
    op: Literal["move_block"]
    section_id: Identifier
    index: int = Field(ge=0, le=60, strict=True)


class AddBlock(ContractModel):
    op: Literal["add_block"]
    section_id: Identifier
    index: int = Field(ge=0, le=60, strict=True)
    block: EditableBlock


class SectionTarget(ContractModel):
    section_id: Identifier


class SetLayout(SectionTarget):
    op: Literal["set_layout"]
    layout: Literal["stack", "image_left", "image_right", "grid"]


class RemoveSection(SectionTarget):
    op: Literal["remove_section"]


class MoveSection(SectionTarget):
    op: Literal["move_section"]
    index: int = Field(ge=0, le=29, strict=True)


class AddSection(ContractModel):
    op: Literal["add_section"]
    section: EditableSection
    index: int = Field(ge=0, le=30, strict=True)


Operation = Annotated[
    ReplaceText
    | ReplaceImage
    | EditImage
    | SetStyle
    | ReplaceTable
    | RemoveBlock
    | MoveBlock
    | AddBlock
    | SetLayout
    | RemoveSection
    | MoveSection
    | AddSection,
    Field(discriminator="op"),
]


class RevisionProposal(ContractModel):
    request_id: Identifier
    base_revision: int = Field(ge=1, strict=True)
    base_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    instruction: FactText
    decision: Literal["ready", "needs_clarification"]
    # 사용자에게 그대로 보여줄 한국어 한 문장. 무엇을 바꿨는지 또는 왜 못 바꾸는지 설명한다.
    # 채팅에서 온 수정안은 항상 채워지고, 코드가 직접 만든 수정안은 비어 있을 수 있다.
    reply: str = ""
    question: FactText | None = None
    operations: list[Operation] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def consistent_decision(self):
        if self.decision == "needs_clarification":
            if not self.question or self.operations:
                raise ValueError("확인이 필요하면 질문만 반환하고 수정하지 않습니다")
        elif not self.operations or self.question is not None:
            raise ValueError("ready에는 수정 작업이 필요하며 질문은 없어야 합니다")
        return self


class ChatTurn(ContractModel):
    """에디터 왼쪽 대화창의 한 턴.

    내용은 사용자가 쓴 글이므로 지시가 아니라 맥락 데이터로만 다룬다.
    """

    role: Literal["user", "assistant"]
    content: FactText


def summarize_changes(changes: list[dict]) -> str:
    """화면 하단에 쓸 변경 요약을 코드로 만든다.

    모델이 세도록 두면 실제 변경 수와 어긋날 수 있어 미리보기 결과에서 직접 센다.
    """
    if not changes:
        return "변경 없음"
    labels = {
        "replace_text": "문구",
        "replace_image": "이미지",
        "edit_image": "이미지 편집",
        "set_style": "스타일",
        "replace_table": "정보 표",
        "remove_block": "블록 삭제",
        "move_block": "블록 이동",
        "add_block": "블록 추가",
        "set_layout": "배치",
        "remove_section": "섹션 삭제",
        "move_section": "섹션 이동",
        "add_section": "섹션 추가",
    }
    counts: dict[str, int] = {}
    for change in changes:
        name = labels.get(change.get("op", ""), change.get("op", "변경"))
        counts[name] = counts.get(name, 0) + 1
    return " · ".join(f"{name} {count}건" for name, count in counts.items())


class RevisionPreviewRequest(ContractModel):
    document: EditableDocument
    proposal: RevisionProposal


class ImageEditIntent(ContractModel):
    block_id: BlockIdentifier
    source_asset_id: Identifier
    instruction: FactText
    status: Literal["not_started"] = "not_started"


class RevisionPreviewResult(ContractModel):
    status: Literal["needs_review", "needs_clarification"]
    document: EditableDocument
    document_sha256: str
    reply: str = ""
    footer: str = "변경 없음"
    question: str | None = None
    changes: list[dict] = Field(default_factory=list)
    image_edit_intents: list[ImageEditIntent] = Field(default_factory=list)
    persisted: Literal[False] = False
    model_calls: Literal[0] = 0
    warnings: list[str] = Field(default_factory=list)


class RevisionRenderRequest(RevisionPreviewRequest):
    """승인 전 수정안과 브라우저가 읽을 자산 경로를 함께 검증한다."""

    asset_urls: dict[Identifier, SafeSameOriginAssetUrl] = Field(max_length=50)


class RevisionRenderResult(ContractModel):
    preview: RevisionPreviewResult
    html: str | None
    html_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None
    persisted: Literal[False] = False
    model_calls: Literal[0] = 0
    image_generation_calls: Literal[0] = 0
    note: str = "승인 전 HTML 미리보기입니다. 문서·이미지·파일은 저장하지 않았습니다."

    @model_validator(mode="after")
    def html_matches_status(self):
        has_html = self.html is not None and self.html_sha256 is not None
        if has_html != (self.preview.status == "needs_review"):
            raise ValueError("검토 가능한 수정안에만 HTML 미리보기가 있어야 합니다")
        return self
