from __future__ import annotations

import json
import time
from pathlib import Path

from ad_service.api.schemas.generation import (
    GeneratedAsset,
    GenerationRequest,
    GenerationResult,
    RunMetrics,
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
        image_path = request.resolved_image_path(base_dir)
        if not image_path.is_file():
            raise FileNotFoundError(f"product image does not exist: {image_path}")

        copy_output = self.copy_provider.generate(request)
        self.ledger.ensure_available(copy_output.metrics.estimated_cost_usd)
        self.ledger.record(copy_output.metrics.estimated_cost_usd)
        bbox = request.product_bbox.as_tuple() if request.product_bbox else None
        cutout = self.background_remover.remove(image_path, bbox)
        cutout_path = run_dir / "product_cutout.png"
        cutout.save(cutout_path)

        assets: list[GeneratedAsset] = []
        total_cost = copy_output.metrics.estimated_cost_usd
        for asset_type, (width, height) in ASSET_SIZES.items():
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
            composed, safe_area = compose_product(image_output.image, cutout, asset_type)
            final_image = render_korean_copy(composed, copy_output.value, asset_type, safe_area)
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
            copy=copy_output.value,
            assets=assets,
            metrics=RunMetrics(
                latency_ms=int((time.perf_counter() - started) * 1000),
                estimated_cost_usd=total_cost,
                copy_model=self.copy_provider.name,
                image_model=self.image_provider.name,
                background_remover=self.background_remover.name,
            ),
            warnings=[],
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
