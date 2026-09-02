from __future__ import annotations

import json
import time
from pathlib import Path

from ad_service.api.schemas.generation import (
    AssetType,
    GeneratedAsset,
    GenerationRequest,
    GenerationResult,
    OutputType,
    RunMetrics,
    SafeArea,
)
from ad_service.core.budget import BudgetLedger
from ad_service.models.base import BackgroundRemover, CopyProvider, ImageProvider
from ad_service.models.image_generator import GPT_IMAGE_2_PRICES, OpenAIImageProvider
from ad_service.prompts.templates import build_image_prompt
from ad_service.utils.image_utils import (
    ASSET_SIZES,
    compose_product,
    render_korean_copy,
)


class GenerationPipeline:
    def __init__(
        self,
        copy_provider: CopyProvider,
        image_provider: ImageProvider,
        background_remover: BackgroundRemover,
        output_root: Path,
        budget_cap_usd: float = 10.0,
    ) -> None:
        self.copy_provider = copy_provider
        self.image_provider = image_provider
        self.background_remover = background_remover
        self.output_root = output_root
        self.ledger = BudgetLedger(output_root / "budget.json", budget_cap_usd)

    def _log(self, payload: dict[str, object]) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        with (self.output_root / "experiment.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def generate(
        self,
        request: GenerationRequest,
        seed: int = 0,
        base_dir: Path | None = None,
    ) -> GenerationResult:
        started = time.perf_counter()
        run_dir = self.output_root / request.request_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # 이미지 입력은 선택 사항입니다. 경로가 들어온 경우에만 실제 파일인지 확인합니다.
        image_path = request.resolved_image_path(base_dir)
        if image_path is not None and not image_path.is_file():
            raise FileNotFoundError(f"product image does not exist: {image_path}")

        warnings: list[str] = []
        total_cost = 0.0

        # 사용자가 copy를 요청했을 때만 언어 모델을 호출합니다.
        # 이미지 결과만 필요한 요청에서 불필요한 API 비용이 발생하지 않게 하기 위함입니다.
        copy_output = None
        if OutputType.COPY in request.outputs:
            copy_output = self.copy_provider.generate(request)
            self.ledger.ensure_available(copy_output.metrics.estimated_cost_usd)
            self.ledger.record(copy_output.metrics.estimated_cost_usd)
            total_cost += copy_output.metrics.estimated_cost_usd

        # 이미지가 들어오면 배경을 제거한 제품 컷을 한 번만 만들고 모든 규격에 재사용합니다.
        cutout = None
        if image_path is not None:
            bbox = request.image_bbox.as_tuple() if request.image_bbox else None
            cutout = self.background_remover.remove(image_path, bbox)
            cutout_path = run_dir / "product_cutout.png"
            cutout.save(cutout_path)

        requested_assets = [
            AssetType(output.value) for output in request.outputs if output is not OutputType.COPY
        ]
        if image_path is None and OutputType.PRODUCT_IMAGE in request.outputs:
            warnings.append(
                "원본 이미지가 없어 제품 모습은 텍스트 설명을 바탕으로 추정 생성되었습니다."
            )

        assets: list[GeneratedAsset] = []
        for asset_type in requested_assets:
            width, height = ASSET_SIZES[asset_type]
            prompt = build_image_prompt(request, asset_type)
            estimate = 0.0
            if isinstance(self.image_provider, OpenAIImageProvider):
                estimate = GPT_IMAGE_2_PRICES.get(self.image_provider.quality, {}).get(
                    f"{width}x{height}",
                    0.25,
                )
                self.ledger.ensure_available(estimate)
            image_output = self.image_provider.generate_background(
                request=request,
                asset_type=asset_type.value,
                width=width,
                height=height,
                prompt=prompt,
                seed=seed,
            )
            self.ledger.record(image_output.metrics.estimated_cost_usd)
            total_cost += image_output.metrics.estimated_cost_usd
            background_path = run_dir / f"{asset_type.value}_background.png"
            image_output.image.save(background_path)

            if cutout is not None:
                # 원본 제품이 있으면 AI가 만든 배경 위에 실제 제품 컷을 합성합니다.
                composed, safe_area = compose_product(image_output.image, cutout, asset_type)
            else:
                # 텍스트만 들어온 경우에는 이미지 모델의 결과 전체를 사용합니다.
                composed = image_output.image
                safe_area = _default_safe_area(asset_type, width, height)

            # 문구 결과가 함께 생성된 경우에만 한글 미리보기를 이미지 위에 그립니다.
            if copy_output is not None:
                final_image = render_korean_copy(
                    composed,
                    copy_output.value,
                    asset_type,
                    safe_area,
                )
            else:
                final_image = composed.convert("RGB")
            final_path = run_dir / f"{asset_type.value}.png"
            final_image.save(final_path)
            assets.append(
                GeneratedAsset(
                    type=asset_type,
                    path=str(final_path),
                    width=width,
                    height=height,
                    model=self.image_provider.name,
                    prompt=prompt,
                    seed=seed,
                    text_safe_area=safe_area,
                    latency_ms=image_output.metrics.latency_ms,
                    estimated_cost_usd=image_output.metrics.estimated_cost_usd,
                )
            )
            self._log(
                {
                    "request_id": request.request_id,
                    "stage": "image",
                    "asset_type": asset_type.value,
                    "model": self.image_provider.name,
                    "seed": seed,
                    "latency_ms": image_output.metrics.latency_ms,
                    "estimated_cost_usd": image_output.metrics.estimated_cost_usd,
                    "status": "success",
                    "path": str(final_path),
                }
            )

        result = GenerationResult(
            request_id=request.request_id,
            mode=request.input_mode,
            copy=copy_output.value if copy_output is not None else None,
            assets=assets,
            metrics=RunMetrics(
                latency_ms=int((time.perf_counter() - started) * 1000),
                estimated_cost_usd=total_cost,
                copy_model=self.copy_provider.name if copy_output is not None else None,
                image_model=self.image_provider.name if requested_assets else None,
                background_remover=self.background_remover.name if cutout is not None else None,
            ),
            warnings=warnings,
        )
        (run_dir / "result.json").write_text(
            result.model_dump_json(indent=2),
            encoding="utf-8",
        )
        self._log(
            {
                "request_id": request.request_id,
                "stage": "complete",
                "copy_model": self.copy_provider.name,
                "image_model": self.image_provider.name,
                "latency_ms": result.metrics.latency_ms,
                "estimated_cost_usd": total_cost,
                "status": "success",
            }
        )
        return result


def _default_safe_area(
    asset_type: AssetType,
    width: int,
    height: int,
) -> SafeArea | None:
    """텍스트 전용 이미지에서 한글을 올릴 기본 공간을 계산합니다.

    제품 이미지에는 광고 문구를 넣지 않으므로 안전 영역이 필요하지 않습니다.
    """

    if asset_type is AssetType.BANNER:
        return SafeArea(x=70, y=90, width=int(width * 0.46), height=int(height * 0.68))
    if asset_type is AssetType.DETAIL_VISUAL:
        return SafeArea(x=80, y=70, width=width - 160, height=int(height * 0.20))
    return None


def generate(
    request: GenerationRequest,
    copy_provider: CopyProvider,
    image_provider: ImageProvider,
    background_remover: BackgroundRemover,
    output_root: Path,
    seed: int = 0,
    budget_cap_usd: float = 10.0,
    base_dir: Path | None = None,
) -> GenerationResult:
    pipeline = GenerationPipeline(
        copy_provider=copy_provider,
        image_provider=image_provider,
        background_remover=background_remover,
        output_root=output_root,
        budget_cap_usd=budget_cap_usd,
    )
    return pipeline.generate(request=request, seed=seed, base_dir=base_dir)
