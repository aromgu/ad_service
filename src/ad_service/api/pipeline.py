"""생성 파이프라인 인터페이스와 목(mock) 구현.

API 계층은 이 `GenerationPipeline` 프로토콜만 알면 된다.
실제 VLM / 이미지 생성 연결은 모델 담당이 같은 프로토콜을 구현해서 끼운다
(`cjpark-model-baseline` 브랜치의 `pipelines/inference.py` 가 그 자리).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw

from ad_service.api.schemas.generation import (
    CopyResult,
    GeneratedAsset,
    GenerationRequest,
    GenerationResult,
    InputMode,
    OutputType,
    RunMetrics,
    SafeArea,
)

# 배너 규격 (configs/model_config.yaml asset_sizes 와 맞춤).
_BANNER_SIZE = (1536, 1024)


class GenerationInput:
    """파이프라인에 넘기는 정규화된 입력."""

    def __init__(self, request: GenerationRequest, image_path: Path | None) -> None:
        self.request = request
        self.image_path = image_path

    @property
    def mode(self) -> InputMode:
        has_text = self.request.text is not None
        has_image = self.image_path is not None
        if has_text and has_image:
            return InputMode.TEXT_AND_IMAGE
        if has_image:
            return InputMode.IMAGE_ONLY
        return InputMode.TEXT_ONLY


class GenerationPipeline(Protocol):
    def generate(self, data: GenerationInput, output_dir: Path) -> GenerationResult: ...


def build_pipeline(copy_provider: str, image_provider: str) -> GenerationPipeline:
    """설정값(`AD_COPY_PROVIDER` / `AD_IMAGE_PROVIDER`)으로 파이프라인을 고른다.

    모델 담당(cjpark)은 실제 파이프라인을 이 함수에 등록한다. 예::

        if copy_provider != "mock":
            from ad_service.pipelines.inference import GenerationPipeline as RealPipeline
            return RealPipeline(...)

    자세한 내용은 docs/model_integration.md.
    """

    if copy_provider == "mock" and image_provider == "mock":
        return MockPipeline()
    raise NotImplementedError(
        f"provider copy={copy_provider!r} image={image_provider!r} 는 아직 연결되지 않았습니다. "
        "docs/model_integration.md 참고."
    )


class MockPipeline:
    """비용 없이 전체 흐름을 검증하기 위한 가짜 파이프라인.

    문구는 입력 텍스트를 재활용한 고정 템플릿, 배너는 Pillow 로 그린 플레이스홀더 PNG.
    """

    copy_model = "mock-copy-v0"
    image_model = "mock-image-v0"

    def generate(self, data: GenerationInput, output_dir: Path) -> GenerationResult:
        started = time.perf_counter()
        request = data.request
        outputs = set(request.outputs)
        summary_src = request.text or (data.image_path.name if data.image_path else "상품")

        copy_result: CopyResult | None = None
        if OutputType.COPY in outputs:
            copy_result = self._mock_copy(summary_src, request)

        assets: list[GeneratedAsset] = []
        if OutputType.BANNER in outputs:
            assets.append(self._mock_banner(summary_src, output_dir))

        latency_ms = int((time.perf_counter() - started) * 1000)
        return GenerationResult(
            mode=data.mode,
            copy=copy_result,
            assets=assets,
            metrics=RunMetrics(
                latency_ms=latency_ms,
                estimated_cost_usd=0.0,
                copy_model=self.copy_model if copy_result else None,
                image_model=self.image_model if assets else None,
            ),
            warnings=["목 파이프라인 결과입니다. 실제 모델이 연결되면 교체됩니다."],
        )

    # -- 내부 --------------------------------------------------------------------------
    def _mock_copy(self, summary_src: str, request: GenerationRequest) -> CopyResult:
        store = request.options.store_name or "우리 가게"
        short = summary_src[:20]
        return CopyResult(
            product_summary=f"{store}의 {summary_src[:60]}",
            headline_candidates=[
                f"{short}, 지금 만나보세요"[:25],
                f"{store} 추천 {short}"[:25],
                f"오늘의 {short}"[:25],
            ],
            body_candidates=[
                f"{summary_src[:80]}"[:90],
                f"{store}에서 준비한 {short}. 지금 확인하세요."[:90],
                f"{request.options.tone or '정성껏'} 만든 {short}."[:90],
            ],
            cta_candidates=["구매하기", "담기", "더보기"],
            keywords=[w for w in summary_src.split()[:5]] or ["광고"],
        )

    def _mock_banner(self, summary_src: str, output_dir: Path) -> GeneratedAsset:
        started = time.perf_counter()
        output_dir.mkdir(parents=True, exist_ok=True)
        width, height = _BANNER_SIZE

        img = Image.new("RGB", (width, height), (245, 240, 235))
        draw = ImageDraw.Draw(img)
        draw.rectangle([40, 40, width - 40, height - 40], outline=(180, 120, 90), width=6)
        draw.text((80, 80), "MOCK BANNER", fill=(120, 80, 60))
        draw.text((80, 140), summary_src[:60], fill=(60, 60, 60))

        path = output_dir / "banner.png"
        img.save(path, format="PNG")
        latency_ms = int((time.perf_counter() - started) * 1000)

        return GeneratedAsset(
            type=OutputType.BANNER,
            url="",  # 라우터가 request_id 를 알고 나서 /api/v1/assets/... 로 채운다
            width=width,
            height=height,
            model=self.image_model,
            seed=None,
            text_safe_area=SafeArea(x=80, y=80, width=width - 160, height=280),
            latency_ms=latency_ms,
            estimated_cost_usd=0.0,
        )
