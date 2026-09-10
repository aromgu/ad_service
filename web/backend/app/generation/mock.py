"""내장 목업 생성기.

실제 VLM/이미지 생성 모델 대신 폼 입력을 재료로 그럴듯한 결과물을 만들어 낸다.
스텝 진행·소요 시간까지 흉내 내므로 생성 중 화면(2b·3b·4b)을 실제 서버 이벤트로 검증할 수 있다.

세 가지 작업 타입을 지원한다:
- detail_page — 상세페이지 문서
- blog        — 네이버 블로그 포스트 초안
- product_reg — 상품등록 정보 (문서가 아니라 등록 필드 묶음)
"""

import asyncio
import random
import uuid
from typing import Any

from app.generation.base import DocumentDraft, ImageRef, ProductDraftData, ProgressCallback

STEPS: dict[str, list[dict[str, str]]] = {
    "detail_page": [
        {"key": "analyze", "label": "상품 정보 분석"},
        {"key": "copy", "label": "카피 문구 작성"},
        {"key": "layout", "label": "레이아웃 구성"},
        {"key": "images", "label": "이미지 배치"},
    ],
    "blog": [
        {"key": "keywords", "label": "주제·키워드 분석"},
        {"key": "outline", "label": "목차 구성"},
        {"key": "body", "label": "본문 작성"},
        {"key": "photos", "label": "사진 배치 · 태그 추천"},
    ],
    "product_reg": [
        {"key": "ocr", "label": "이미지 OCR 추출"},
        {"key": "category", "label": "브랜드 · 카테고리 분류"},
        {"key": "naming", "label": "상품명 · 태그 생성"},
        {"key": "options", "label": "옵션 · KC인증 판별"},
    ],
}

# 톤별 히어로 카피 뼈대. {product} / {benefit} 치환.
_HEADLINES = {
    "감성적": ["무너진 장벽을 다시 세우는", "4주간의 기록,", "피부가 먼저 답합니다"],
    "정보 중심": ["{product}", "핵심 성분과 사용법을", "숫자로 정리했습니다"],
}
_SUBCLAIMS = {
    "감성적": "민감한 피부도 매일 쓸 수 있도록, 향료와 색소를 뺐습니다.",
    "정보 중심": "성분표와 임상 데이터를 그대로 공개합니다. 직접 확인하고 판단하세요.",
}


def _sid() -> str:
    return uuid.uuid4().hex[:12]


def _first_feature(features: str) -> str:
    for sep in (",", "·", "\n"):
        if sep in features:
            return features.split(sep)[0].strip()
    return features.strip()[:40]


def _eyebrow(product_name: str) -> str:
    """상품명을 인쇄물 톤의 eyebrow(대문자 + 넓은 자간)로."""
    ascii_only = "".join(ch for ch in product_name if ch.isascii()).strip()
    return (ascii_only or product_name).upper()


class MockProvider:
    name = "mock"

    def __init__(self, duration_seconds: float = 12.0, sample_urls: list[str] | None = None):
        self.duration_seconds = max(duration_seconds, 1.0)
        self.sample_urls = sample_urls or []

    def steps(self, job_type: str) -> list[dict[str, str]]:
        return [dict(s) for s in STEPS.get(job_type, STEPS["detail_page"])]

    async def generate(
        self,
        *,
        job_type: str,
        form: dict[str, Any],
        images: list[ImageRef],
        on_progress: ProgressCallback,
    ) -> DocumentDraft | ProductDraftData:
        steps = self.steps(job_type)
        per_step = self.duration_seconds / len(steps)
        # 스텝 안에서도 진행률이 조금씩 오르도록 잘게 쪼개 보고한다.
        ticks = 6
        for i, step in enumerate(steps):
            for t in range(ticks):
                await asyncio.sleep(per_step / ticks)
                await on_progress(step["key"], (i + (t + 1) / ticks) / len(steps))
            await on_progress(step["key"], (i + 1) / len(steps))

        if job_type == "blog":
            return self._build_blog(form=form, images=images)
        if job_type == "product_reg":
            return self._build_product(form=form, images=images)
        return self._build_detail(form=form, images=images)

    # ---------- 상세페이지 (2c) ----------
    def _build_detail(self, *, form: dict[str, Any], images: list[ImageRef]) -> DocumentDraft:
        product = form.get("product_name") or "이름 없는 상품"
        tone = form.get("tone") or "감성적"
        target = form.get("target") or "전체"
        features = form.get("features") or ""
        benefit = _first_feature(features) or "핵심 효능"

        headline = [
            line.format(product=product, benefit=benefit)
            for line in _HEADLINES.get(tone, _HEADLINES["감성적"])
        ]
        urls = [img.url for img in images] or self.sample_urls
        hero_url = urls[0] if urls else None

        sections: list[dict[str, Any]] = [
            {"id": _sid(), "type": "eyebrow", "visible": True, "content": {"text": _eyebrow(product)}},
            {"id": _sid(), "type": "headline", "visible": True, "content": {"lines": headline, "fontSize": 42}},
            {
                "id": _sid(),
                "type": "stat",
                "visible": True,
                "content": {"prefix": benefit, "value": "+38%", "suffix": "· 4주 사용 후 임상 결과"},
            },
            {
                "id": _sid(),
                "type": "subclaim",
                "visible": True,
                "content": {"text": _SUBCLAIMS.get(tone, _SUBCLAIMS["감성적"])},
            },
            {
                "id": _sid(),
                "type": "image",
                "visible": True,
                "content": {"url": hero_url, "alt": f"{product} 제품 사진", "height": 360},
            },
            {"id": _sid(), "type": "note", "visible": True, "content": {"text": "— 핵심 성분 섹션 이어짐 —"}},
        ]

        messages = [
            {"role": "user", "content": f"{product} 상세페이지 만들어줘. {target} 타겟이야.", "meta": {}},
            {
                "role": "assistant",
                "content": "업로드하신 이미지를 확인했어요. 성분 정보와 사용 장면을 기준으로 구성안을 잡아볼게요.",
                "meta": {
                    "toolSteps": [f"Listing files, Viewing image ×{max(len(urls), 1)}"],
                    "askUser": True,
                    "summaryCard": [
                        {"label": "채널", "value": "스마트스토어"},
                        {"label": "상품", "value": product},
                        {"label": "섹션", "value": f"히어로 외 {max(len(sections) - 1, 0)}개"},
                        {"label": "톤", "value": tone},
                    ],
                    "closing": "히어로 카피는 임상 수치를 앞세워 신뢰감을 주는 방향으로 잡았습니다. 수정할 부분을 알려주세요.",
                    "footer": f"{len(sections)}개 파일 생성됨",
                },
            },
        ]

        return DocumentDraft(
            title=f"{product} 상세페이지",
            sections=sections,
            thumbnail_url=hero_url,
            messages=messages,
        )

    # ---------- 블로그 (3c) ----------
    def _build_blog(self, *, form: dict[str, Any], images: list[ImageRef]) -> DocumentDraft:
        topic = form.get("topic") or "이름 없는 주제"
        style = form.get("style") or "기본 블로그"
        extra = (form.get("extra_request") or "").strip()
        urls = [img.url for img in images] or self.sample_urls

        sections: list[dict[str, Any]] = [
            {
                "id": _sid(),
                "type": "eyebrow",
                "visible": True,
                "content": {"text": f"네이버 블로그 포스트 · 초안", "letterSpacing": "0.18em"},
            },
            {
                "id": _sid(),
                "type": "headline",
                "visible": True,
                "content": {
                    "lines": [f"{topic} 추천,", "직접 3주 써보고 남기는 기록"],
                    "fontSize": 34,
                },
            },
            {
                "id": _sid(),
                "type": "paragraph",
                "visible": True,
                "content": {
                    "text": (
                        f"{topic}을(를) 고르면서 가장 고민됐던 부분을 먼저 적어 둡니다. "
                        "실제로 여러 번 써보며 확인한 내용을 순서대로 정리했습니다."
                    )
                },
            },
            {
                "id": _sid(),
                "type": "heading",
                "visible": True,
                "content": {"text": "1. 사기 전에 이것부터 확인하세요"},
            },
            {
                "id": _sid(),
                "type": "paragraph",
                "visible": True,
                "content": {
                    "text": "실물을 받아보기 전에 크기와 무게를 먼저 재보는 편이 빠릅니다. 사용 환경에 맞는지가 만족도를 가장 크게 좌우했습니다."
                },
            },
            {
                "id": _sid(),
                "type": "image",
                "visible": True,
                "content": {"url": urls[0] if urls else None, "alt": f"{topic} 사진 1", "height": 260, "caption": "사진 1"},
            },
            {
                "id": _sid(),
                "type": "heading",
                "visible": True,
                "content": {"text": "2. 실제로 써보니 이런 점이 좋았습니다"},
            },
            {"id": _sid(), "type": "note", "visible": True, "content": {"text": "— 소제목 2개 더 이어짐 —"}},
        ]

        # 요약 카드 숫자는 실제 문서 내용에서 센다.
        # (에디터 상단 바의 글자 수 지표와 어긋나면 사용자가 혼란스럽다)
        def _text(sec: dict[str, Any]) -> str:
            c = sec["content"]
            return " ".join(
                str(v) for v in [c.get("text"), *(c.get("lines") or [])] if v
            )

        char_count = sum(len(_text(s)) for s in sections)
        headings = len([s for s in sections if s["type"] == "heading"])

        user_msg = extra or f"{topic}에 대한 블로그 글 써줘."
        messages = [
            {"role": "user", "content": user_msg, "meta": {}},
            {
                "role": "assistant",
                "content": f"업로드하신 사진 {max(len(urls), 1)}장을 확인했어요. 독자가 궁금해할 순서로 목차를 잡았습니다.",
                "meta": {
                    "toolSteps": [f"키워드 조사, 사진 {max(len(urls), 1)}장 분석"],
                    "summaryCard": [
                        {"label": "스타일", "value": style},
                        {"label": "글자 수", "value": f"약 {char_count:,}자"},
                        {"label": "소제목", "value": f"{headings}개"},
                        {"label": "사진", "value": f"{len([s for s in sections if s['type'] == 'image'])}장 배치"},
                    ],
                    "closing": "제목은 검색 노출을 고려해 핵심 키워드를 앞에 뒀습니다. 고칠 부분을 알려주세요.",
                    "footer": "초안 1개 생성됨",
                },
            },
        ]

        return DocumentDraft(
            title=f"{topic} 블로그",
            sections=sections,
            thumbnail_url=urls[0] if urls else None,
            messages=messages,
        )

    # ---------- 상품등록 (4c) ----------
    def _build_product(self, *, form: dict[str, Any], images: list[ImageRef]) -> ProductDraftData:
        urls = [img.url for img in images] or self.sample_urls
        info = (form.get("product_info") or "").strip()
        shipping = form.get("shipping") or {}

        # 직접 입력한 상품 정보가 있으면 AI 분석보다 우선 적용한다(4a 안내 문구).
        # 다만 "구성품 본체 1개 · 소재 캔버스" 같은 스펙 나열은 상품명이 아니라
        # 설명 재료로만 쓴다 — 그대로 이름에 넣으면 상품명이 엉망이 된다.
        brand = "PARK HERE"
        base_name = "페이즐리 에코백 여성 데일리 숄더백 캔버스 가방 43×36cm"
        first = info.splitlines()[0].strip() if info else ""
        looks_like_a_name = bool(first) and len(first) <= 40 and not any(
            marker in first for marker in ("·", ":", "|", "／", "/")
        )
        if looks_like_a_name:
            base_name = first

        ocr_chars = 320 + len(info) + len(urls) * 24

        return ProductDraftData(
            analysis={
                "image_count": len(urls),
                "ocr_chars": ocr_chars,
                "source": "직접 입력 우선 적용" if info else "이미지 OCR 분석",
            },
            description=(
                f"{brand} 브랜드의 상품입니다. 데일리용으로 가볍고 실용적이며, "
                "상세 이미지에서 추출한 정보를 바탕으로 작성했습니다."
                + (f"\n\n입력하신 정보: {info}" if info else "")
            ),
            image_urls=urls,
            representative_image_url=urls[0] if urls else None,
            product_name=f"{brand.split()[0]} {base_name}"[:100],
            brand=brand,
            manufacturer=brand,
            seller_code=f"DGG-{random.randint(10000000, 99999999)}",
            category_candidates=[
                {"path": "패션잡화 › 여성가방 › 에코백", "confidence": 95},
                {"path": "패션잡화 › 남성가방 › 에코백", "confidence": 95},
                {"path": "출산/육아 › 유아동잡화 › 가방 › 토트백/숄더백", "confidence": 81},
            ],
            selected_category="패션잡화 › 여성가방 › 에코백",
            price=None,
            shipping_fee=int(shipping.get("shipping_fee", 3000)),
            stock=999,
            options=[
                {"name": "화이트", "price": 0, "stock": 9838},
                {"name": "블랙", "price": 0, "stock": 9685},
            ],
            kc={"mode": "none", "detail": "KC 대상 아님", "cert_number": ""},
            tags=["에코백", "에코백가방", "여자가방", "크로스백", "페이즐리", "캔버스백"],
            attributes={"사용대상": "여성", "패턴": "프린트", "주요소재": "캔버스"},
        )

    # ---------- 채팅 수정 ----------
    def revise(
        self, *, message: str, sections: list[dict[str, Any]]
    ) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        """채팅 요청에 대한 (응답문, meta, 수정된 sections).

        실제 모델이 붙기 전까지의 규칙 기반 목업이다. 와이어프레임 2d 의
        "히어로 문구를 짧게" 시나리오를 실제로 동작시킨다.
        """
        revised = [dict(s) for s in sections]
        head = next((s for s in revised if s["type"] == "headline"), None)

        if any(k in message for k in ("짧", "줄여", "줄이")) and head:
            lines = list(head["content"].get("lines", []))
            stat = next((s for s in revised if s["type"] == "stat"), None)
            if stat:
                prefix = stat["content"].get("prefix", "")
                value = stat["content"].get("value", "")
                new_lines = [f"{prefix} {value},".strip(), lines[-1] if lines else "4주간의 기록"]
            else:
                # 블로그처럼 stat 이 없는 문서는 마지막 줄만 남긴다.
                new_lines = [lines[0]] if lines else ["제목"]
            head["content"] = {**head["content"], "lines": new_lines, "fontSize": 38}
            return (
                "헤드라인을 더 짧게 줄이고 핵심을 앞으로 당겼어요. "
                "직접 고치시려면 오른쪽 편집 도구를 사용하세요.",
                {"toolSteps": ["Editing hero.section"], "footer": "1개 파일 수정됨"},
                revised,
            )

        if any(k in message for k in ("길게", "늘려", "자세")) and head:
            lines = list(head["content"].get("lines", []))
            head["content"] = {**head["content"], "lines": lines + ["매일 쓰는 루틴으로."]}
            return (
                "헤드라인에 한 줄을 더해 리듬을 살렸어요.",
                {"toolSteps": ["Editing hero.section"], "footer": "1개 파일 수정됨"},
                revised,
            )

        return (
            "요청을 확인했어요. 지금은 목업 생성기라 문구 길이 조절(짧게/길게)만 실제로 반영됩니다. "
            "모델 서버가 연결되면 전체 수정 요청을 처리합니다.",
            {"toolSteps": ["Reading document"], "footer": "변경 없음"},
            revised,
        )
