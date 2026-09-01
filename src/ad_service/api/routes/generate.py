from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from ad_service.api.schemas.generation import GenerationRequest, GenerationResult
from ad_service.core.budget import BudgetExceededError
from ad_service.core.config import get_settings
from ad_service.factory import (
    create_background_remover,
    create_copy_provider,
    create_image_provider,
)
from ad_service.pipelines.inference import GenerationPipeline

router = APIRouter(prefix="/v1", tags=["generation"])


@lru_cache
def get_pipeline() -> GenerationPipeline:
    settings = get_settings()
    return GenerationPipeline(
        copy_provider=create_copy_provider(settings.copy_provider),
        image_provider=create_image_provider(settings.image_provider, settings.image_quality),
        background_remover=create_background_remover(settings.background_remover),
        output_root=settings.output_root,
        budget_cap_usd=settings.budget_cap_usd,
    )


@router.post("/generate", response_model=GenerationResult)
async def generate_asset(request: GenerationRequest) -> GenerationResult:
    try:
        return await run_in_threadpool(
            get_pipeline().generate,
            request,
            0,
            Path.cwd(),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BudgetExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
