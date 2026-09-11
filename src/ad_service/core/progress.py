"""생성 파이프라인과 작업 상태 저장소 사이의 진행 이벤트 계약."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class PipelineStage(str, Enum):
    QUEUED = "queued"
    VALIDATING_INPUT = "validating_input"
    GENERATING_COPY = "generating_copy"
    EXTRACTING_PRODUCT = "extracting_product"
    GENERATING_IMAGES = "generating_images"
    COMPOSITING = "compositing"
    VALIDATING_RESULT = "validating_result"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class PipelineProgress:
    """실제로 시작되거나 끝난 처리 단계만 전달한다."""

    stage: PipelineStage
    message: str
    asset_type: str | None = None
    completed_assets: int | None = None
    total_assets: int | None = None
    model_calls_delta: int = 0
    image_generation_calls_delta: int = 0
    preprocessing_calls_delta: int = 0
    recorded_cost_delta_usd: float = 0.0


ProgressCallback = Callable[[PipelineProgress], None]
CancellationCheck = Callable[[], bool]


class GenerationCancelledError(RuntimeError):
    """취소 요청을 확인한 안전한 체크포인트에서 실행을 중단한다."""
