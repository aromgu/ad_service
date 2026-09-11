from __future__ import annotations

import json
import time
from pathlib import Path

from ad_service.api.schemas.generation import (
    AssetType,
    GeneratedAsset,
    GenerationRequest,
    GenerationResult,
    ImageInputStrategy,
    ImageProcessingRoute,
    OutputType,
    RunMetrics,
    SafeArea,
)
from ad_service.core.budget import BudgetLedger
from ad_service.core.progress import (
    CancellationCheck,
    GenerationCancelledError,
    PipelineProgress,
    PipelineStage,
    ProgressCallback,
)
from ad_service.models.base import BackgroundRemover, CopyProvider, ImageProvider
from ad_service.models.image_generator import GPT_IMAGE_2_PRICES, OpenAIImageProvider
from ad_service.prompts.templates import build_image_prompt, build_reference_edit_prompt
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
        *,
        progress_callback: ProgressCallback | None = None,
        cancellation_check: CancellationCheck | None = None,
    ) -> GenerationResult:
        def emit(progress: PipelineProgress) -> None:
            if progress_callback is not None:
                progress_callback(progress)

        def stop_if_cancelled() -> None:
            if cancellation_check is not None and cancellation_check():
                raise GenerationCancelledError("사용자가 생성을 취소했습니다")

        started = time.perf_counter()
        run_dir = self.output_root / request.request_id
        run_dir.mkdir(parents=True, exist_ok=True)

        stop_if_cancelled()
        emit(PipelineProgress(PipelineStage.VALIDATING_INPUT, "입력 정보를 검증하고 있습니다."))

        # 이미지 입력은 선택 사항입니다. 경로가 들어온 경우에만 실제 파일인지 확인합니다.
        image_path = request.resolved_image_path(base_dir)
        if image_path is not None and not image_path.is_file():
            raise FileNotFoundError(f"product image does not exist: {image_path}")

        warnings: list[str] = []
        total_cost = 0.0
        requested_assets = [
            AssetType(output.value) for output in request.outputs if output is not OutputType.COPY
        ]
        direct_edit = (
            bool(requested_assets)
            and image_path is not None
            and request.options.image_input_strategy is ImageInputStrategy.DIRECT_EDIT
        )

        # 이 값들은 최종 result.json에 함께 저장됩니다. 팀원이 결과만 보더라도 왜 해당
        # 경로가 선택됐는지 알 수 있도록 라우팅 근거를 숨기지 않습니다.
        image_processing_route: ImageProcessingRoute | None = None
        routing_reason: str | None = None
        selected_background_remover: BackgroundRemover | None = None

        if requested_assets and image_path is None:
            image_processing_route = ImageProcessingRoute.TEXT_TO_IMAGE
            routing_reason = "상품 이미지가 없어 사용자 설명으로 전체 이미지를 생성했습니다."
        elif direct_edit:
            image_processing_route = ImageProcessingRoute.DIRECT_EDIT
            routing_reason = "사용자가 direct_edit를 명시해 원본 전체를 이미지 모델로 편집했습니다."
        elif requested_assets and image_path is not None:
            image_processing_route = ImageProcessingRoute.COMPOSITE

        if direct_edit and not self.image_provider.supports_reference_edit:
            raise ValueError(
                f"{self.image_provider.name} 모델은 direct_edit 방식을 지원하지 않습니다"
            )
        stop_if_cancelled()

        # 사용자가 copy를 요청했을 때만 언어 모델을 호출합니다.
        # 이미지 결과만 필요한 요청에서 불필요한 API 비용이 발생하지 않게 하기 위함입니다.
        copy_output = None
        if OutputType.COPY in request.outputs:
            stop_if_cancelled()
            emit(
                PipelineProgress(
                    PipelineStage.GENERATING_COPY,
                    "광고 문구를 생성하고 있습니다.",
                    model_calls_delta=1,
                )
            )
            copy_output = self.copy_provider.generate(request)
            self.ledger.ensure_available(copy_output.metrics.estimated_cost_usd)
            self.ledger.record(copy_output.metrics.estimated_cost_usd)
            total_cost += copy_output.metrics.estimated_cost_usd
            emit(
                PipelineProgress(
                    PipelineStage.GENERATING_COPY,
                    "광고 문구 생성을 완료했습니다.",
                    recorded_cost_delta_usd=copy_output.metrics.estimated_cost_usd,
                )
            )
            stop_if_cancelled()

        # 이미지가 들어오면 배경을 제거한 제품 컷을 한 번만 만들고 모든 규격에 재사용합니다.
        cutout = None
        if requested_assets and image_path is not None and not direct_edit:
            bbox = request.image_bbox.as_tuple() if request.image_bbox else None
            # auto 제거기는 박스가 있으면 SAM2, 없으면 BiRefNet을 반환합니다. 사용자가
            # --remover로 특정 모델을 지정했다면 그 모델을 그대로 사용합니다.
            selected_background_remover = self.background_remover.select_for_bbox(bbox)
            stop_if_cancelled()
            emit(
                PipelineProgress(
                    PipelineStage.EXTRACTING_PRODUCT,
                    "원본 이미지에서 상품 영역을 추출하고 있습니다.",
                    preprocessing_calls_delta=1,
                )
            )
            cutout = selected_background_remover.remove(image_path, bbox)
            cutout_path = run_dir / "product_cutout.png"
            cutout.save(cutout_path)
            stop_if_cancelled()

            if self.background_remover.name == "auto" and bbox is not None:
                routing_reason = "선택 박스가 있어 SAM2로 목표 상품을 추출한 뒤 합성했습니다."
            elif self.background_remover.name == "auto":
                routing_reason = "선택 박스가 없어 BiRefNet으로 주요 상품을 추출한 뒤 합성했습니다."
            else:
                routing_reason = (
                    f"사용자가 지정한 {selected_background_remover.name} 모델로 상품을 "
                    "추출한 뒤 합성했습니다."
                )

        if direct_edit:
            warnings.append(
                "직접 편집은 생성형 모델이 포장 글자·로고를 바꿀 수 있으므로 "
                "원본과 비교 검수가 필요합니다."
            )
            if request.image_bbox is not None:
                warnings.append("direct_edit에서는 image_bbox가 사용되지 않습니다.")

        if image_path is None and OutputType.PRODUCT_IMAGE in request.outputs:
            warnings.append(
                "원본 이미지가 없어 제품 모습은 텍스트 설명을 바탕으로 추정 생성되었습니다."
            )

        assets: list[GeneratedAsset] = []
        for asset_index, asset_type in enumerate(requested_assets):
            width, height = ASSET_SIZES[asset_type]
            prompt = (
                build_reference_edit_prompt(request, asset_type)
                if direct_edit
                else build_image_prompt(request, asset_type)
            )
            estimate = 0.0
            if isinstance(self.image_provider, OpenAIImageProvider):
                estimate = GPT_IMAGE_2_PRICES.get(self.image_provider.quality, {}).get(
                    f"{width}x{height}",
                    0.25,
                )
                self.ledger.ensure_available(estimate)
            stop_if_cancelled()
            emit(
                PipelineProgress(
                    PipelineStage.GENERATING_IMAGES,
                    f"{asset_type.value} 이미지를 생성하고 있습니다.",
                    asset_type=asset_type.value,
                    completed_assets=asset_index,
                    total_assets=len(requested_assets),
                    model_calls_delta=1,
                    image_generation_calls_delta=1,
                )
            )
            if direct_edit:
                # 원본 사진 전체를 GPT 이미지 편집 API에 보내 완성된 광고 이미지를 받습니다.
                # 이 경로에서는 BiRefNet/SAM2 배경 제거와 별도 합성을 사용하지 않습니다.
                image_output = self.image_provider.edit_reference_image(
                    request=request,
                    image_path=image_path,
                    asset_type=asset_type.value,
                    width=width,
                    height=height,
                    prompt=prompt,
                    seed=seed,
                )
            else:
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
            emit(
                PipelineProgress(
                    PipelineStage.GENERATING_IMAGES,
                    f"{asset_type.value} 모델 출력을 받았습니다.",
                    asset_type=asset_type.value,
                    completed_assets=asset_index,
                    total_assets=len(requested_assets),
                    recorded_cost_delta_usd=image_output.metrics.estimated_cost_usd,
                )
            )
            stop_if_cancelled()
            if direct_edit:
                # 모델이 직접 편집한 원본도 따로 보관해 후처리 전후를 비교할 수 있게 합니다.
                edited_path = run_dir / f"{asset_type.value}_reference_edit.png"
                image_output.image.save(edited_path)
            else:
                background_path = run_dir / f"{asset_type.value}_background.png"
                image_output.image.save(background_path)

            emit(
                PipelineProgress(
                    PipelineStage.COMPOSITING,
                    f"{asset_type.value} 결과를 합성하고 있습니다.",
                    asset_type=asset_type.value,
                    completed_assets=asset_index,
                    total_assets=len(requested_assets),
                )
            )
            if direct_edit:
                composed = image_output.image
                safe_area = _default_safe_area(asset_type, width, height)
            elif cutout is not None:
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
                    details=image_output.metrics.raw,
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
                    "details": image_output.metrics.raw,
                    "status": "success",
                    "path": str(final_path),
                }
            )
            emit(
                PipelineProgress(
                    PipelineStage.COMPOSITING,
                    f"{asset_type.value} 결과 저장을 완료했습니다.",
                    asset_type=asset_type.value,
                    completed_assets=asset_index + 1,
                    total_assets=len(requested_assets),
                )
            )
            stop_if_cancelled()

        emit(
            PipelineProgress(
                PipelineStage.VALIDATING_RESULT,
                "생성 결과의 형식과 파일을 검증하고 있습니다.",
                completed_assets=len(assets),
                total_assets=len(requested_assets),
            )
        )
        stop_if_cancelled()
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
                background_remover=(
                    selected_background_remover.name
                    if selected_background_remover is not None
                    else None
                ),
                image_processing_route=image_processing_route,
                routing_reason=routing_reason,
                # copy를 요청하지 않았다면 문구 모델 측정값도 비워 둡니다.
                # 요청했다면 공급자가 돌려준 실제 시간·토큰·세부 측정값을 보존합니다.
                copy_latency_ms=(copy_output.metrics.latency_ms if copy_output else None),
                copy_input_tokens=(copy_output.metrics.input_tokens if copy_output else 0),
                copy_output_tokens=(copy_output.metrics.output_tokens if copy_output else 0),
                copy_details=(copy_output.metrics.raw if copy_output else {}),
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
                "image_processing_route": (
                    image_processing_route.value if image_processing_route is not None else None
                ),
                "routing_reason": routing_reason,
                "latency_ms": result.metrics.latency_ms,
                "estimated_cost_usd": total_cost,
                "status": "success",
            }
        )
        emit(
            PipelineProgress(
                PipelineStage.COMPLETED,
                "요청한 결과 생성을 완료했습니다.",
                completed_assets=len(assets),
                total_assets=len(requested_assets),
            )
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
