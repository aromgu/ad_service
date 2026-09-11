"""편집 문서를 실행 코드 없는 단일 상세페이지 HTML로 렌더링한다."""

from __future__ import annotations

import html
import re
from pathlib import PurePosixPath

from ad_service.api.schemas.revision import EditableBlock, EditableDocument, EditableSection

SAFE_ASSET_URL = re.compile(r"^/?[A-Za-z0-9][A-Za-z0-9_./-]*$")


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _safe_asset_url(value: str) -> str:
    path = PurePosixPath(value)
    if not SAFE_ASSET_URL.fullmatch(value) or ".." in path.parts or value.startswith("//"):
        raise ValueError("이미지 URL은 안전한 동일 출처 경로여야 합니다")
    return value


def _style(block: EditableBlock) -> str:
    style = block.style
    values = [
        f"color:{style.color}",
        f"font-size:{style.font_size}px",
        f"text-align:{style.align}",
        f"width:{style.width_percent}%",
    ]
    if style.background_color.lower() != "#ffffff":
        values.append(f"background-color:{style.background_color}")
    return ";".join(values)


def _render_block(block: EditableBlock, asset_urls: dict[str, str]) -> str:
    content = block.content
    block_id = _escape(content.block_id)
    style = _style(block)
    if content.type == "text":
        tag = {
            "heading": "h2",
            "body": "p",
            "feature": "p",
            "cta": "a",
        }[content.role]
        role_class = f"copy-{content.role}"
        href = ' href="#page-top"' if content.role == "cta" else ""
        return (
            f'<{tag}{href} class="content-block {role_class}" '
            f'data-block-id="{block_id}" style="{style}">{_escape(content.text)}</{tag}>'
        )
    if content.type == "image":
        if content.source_asset_id not in asset_urls:
            raise ValueError(f"이미지 자산 경로가 없습니다: {content.source_asset_id}")
        source = _escape(_safe_asset_url(asset_urls[content.source_asset_id]))
        return (
            f'<figure class="content-block product-figure" data-block-id="{block_id}" '
            f'style="{style}"><img src="{source}" alt="{_escape(content.alt)}" '
            'loading="eager"></figure>'
        )
    rows = "".join(
        f'<tr><th scope="row">{_escape(row.label)}</th><td>{_escape(row.value)}</td></tr>'
        for row in content.rows
    )
    return (
        f'<div class="content-block table-wrap" data-block-id="{block_id}" '
        f'style="{style}"><table><tbody>{rows}</tbody></table></div>'
    )


def _render_section(section: EditableSection, asset_urls: dict[str, str]) -> str:
    rendered = [_render_block(block, asset_urls) for block in section.blocks]
    text = [
        value
        for block, value in zip(section.blocks, rendered, strict=True)
        if block.content.type == "text"
    ]
    visual = [
        value
        for block, value in zip(section.blocks, rendered, strict=True)
        if block.content.type != "text"
    ]
    if section.layout in {"image_left", "image_right"} and visual:
        copy_column = f'<div class="copy-column">{"".join(text)}</div>'
        media_column = f'<div class="media-column">{"".join(visual)}</div>'
        body = (
            media_column + copy_column
            if section.layout == "image_left"
            else copy_column + media_column
        )
    else:
        body = "".join(rendered)
    return (
        f'<section class="detail-section section-{section.kind} layout-{section.layout}" '
        f'data-section-id="{_escape(section.section_id)}">'
        f'<div class="section-inner">{body}</div></section>'
    )


def render_detail_page_html(
    document: EditableDocument,
    asset_urls: dict[str, str],
) -> str:
    """문서와 자산 상대 경로를 스크롤형 상세페이지 HTML로 변환한다."""

    referenced_assets = {
        block.content.source_asset_id
        for section in document.sections
        for block in section.blocks
        if block.content.type == "image"
    }
    missing = referenced_assets - asset_urls.keys()
    if missing:
        raise ValueError(f"이미지 자산 경로가 없습니다: {', '.join(sorted(missing))}")
    for asset_id in referenced_assets:
        _safe_asset_url(asset_urls[asset_id])
    headings = [
        block.content.text
        for section in document.sections
        for block in section.blocks
        if block.content.type == "text" and block.content.role == "heading"
    ]
    title = headings[0] if headings else document.document_id
    sections = "".join(_render_section(section, asset_urls) for section in document.sections)
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)}</title>
  <style>
    :root {{ --wine:#861820; --wine-dark:#4f0e14; --gold:#bd9a64; --ink:#261f1d;
      --muted:#766b67; --paper:#fffdfb; --blush:#f8eeee; --leaf:#eaf1e7; }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; background:#e9e4df; }}
    body {{ margin:0; color:var(--ink); background:#e9e4df;
      font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",
      "Malgun Gothic",sans-serif; word-break:keep-all; overflow-wrap:anywhere; }}
    .page-shell {{ width:min(100%, 920px); margin:0 auto; background:var(--paper);
      box-shadow:0 28px 90px rgba(55,35,30,.13); overflow:hidden; }}
    .detail-section {{ position:relative; padding:96px 72px; border-bottom:1px solid #eee5df; }}
    .section-inner {{ width:100%; max-width:776px; margin:0 auto; }}
    .section-hero {{ min-height:760px; display:flex; align-items:center;
      background:linear-gradient(145deg,#fffafb 0%,var(--blush) 55%,#efe2dc 100%); }}
    .section-story:nth-of-type(2n) {{ background:#fbf8f5; }}
    .section-specifications {{ background:#f4efe9; }}
    .section-custom {{ background:var(--leaf); }}
    .section-cta {{ padding:104px 72px; text-align:center;
      background:linear-gradient(145deg,var(--wine-dark),var(--wine)); }}
    .layout-image_left .section-inner,.layout-image_right .section-inner {{ display:grid;
      grid-template-columns:minmax(0, .9fr) minmax(0, 1.1fr); align-items:center; gap:54px; }}
    .section-hero.layout-image_right .section-inner {{
      grid-template-columns:minmax(0, 1.2fr) minmax(0, .8fr); gap:40px; }}
    .layout-stack .section-inner {{ display:flex; flex-direction:column; align-items:flex-start; }}
    .layout-grid .section-inner {{ display:grid; grid-template-columns:1fr; gap:26px; }}
    .copy-column,.media-column {{ min-width:0; display:flex; flex-direction:column;
      align-items:flex-start; }}
    .content-block {{ max-width:100%; margin-left:0; margin-right:0; }}
    .copy-heading {{ margin-top:0; margin-bottom:28px; line-height:1.2; letter-spacing:-.035em;
      font-family:Georgia,"Times New Roman","Noto Serif KR",serif; font-weight:600; }}
    .section-hero .copy-heading {{ font-size:clamp(38px,5vw,50px)!important;
      color:var(--wine)!important; }}
    .copy-body,.copy-feature {{ margin-top:0; margin-bottom:18px; color:var(--muted)!important;
      font-size:clamp(18px,2.6vw,24px)!important; line-height:1.8; letter-spacing:-.015em; }}
    .product-figure {{ margin-top:0; margin-bottom:0; padding:18px; border-radius:34px;
      background:rgba(255,255,255,.86)!important; box-shadow:0 24px 55px rgba(89,33,30,.14); }}
    .product-figure img {{ display:block; width:100%; height:auto; border-radius:22px; }}
    .table-wrap {{ width:100%!important; margin-top:26px; overflow:hidden; border-radius:22px;
      background:white!important; border:1px solid #e5dad1; }}
    table {{ width:100%; border-collapse:collapse; font-size:18px; line-height:1.55; }}
    th,td {{ padding:22px 24px; vertical-align:top; border-bottom:1px solid #eee5df; }}
    tr:last-child th,tr:last-child td {{ border-bottom:0; }}
    th {{ width:28%; text-align:left; color:var(--wine); font-weight:700; }}
    td {{ color:#554a46; }}
    .section-custom .product-figure {{ width:min(100%,650px)!important; margin:16px auto 0; }}
    .copy-cta {{ display:inline-flex; justify-content:center; align-items:center;
      width:auto!important;
      min-width:260px; margin:0 auto; padding:20px 34px; border-radius:999px;
      color:var(--wine-dark)!important; background:#fff8ef!important; text-decoration:none;
      font-weight:800; box-shadow:0 15px 35px rgba(34,5,7,.25); }}
    @media (max-width:720px) {{
      .detail-section {{ padding:70px 28px; }}
      .layout-image_left .section-inner,.layout-image_right .section-inner {{
        grid-template-columns:1fr;
        gap:38px; }}
      .layout-image_right .copy-column {{ grid-column:1; grid-row:1; }}
      .layout-image_right .media-column {{ grid-column:1; grid-row:2; }}
      .section-hero {{ min-height:auto; }}
      th,td {{ display:block; width:100%; padding:14px 18px; }}
      th {{ padding-bottom:4px; border-bottom:0; }}
      td {{ padding-top:4px; }}
    }}
  </style>
</head>
<body id="page-top">
  <main class="page-shell" data-document-id="{_escape(document.document_id)}"
    data-revision="{document.revision}">{sections}</main>
</body>
</html>
"""
