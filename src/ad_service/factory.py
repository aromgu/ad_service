from __future__ import annotations

from typing import Literal, cast

from ad_service.models.base import BackgroundRemover, CopyProvider, ImageProvider
from ad_service.models.image_generator import (
    FluxImageProvider,
    MockImageProvider,
    OpenAIImageProvider,
)
from ad_service.models.vlm import MockCopyProvider, OpenAICopyProvider, QwenCopyProvider
from ad_service.pipelines.preprocessing import (
    BiRefNetBackgroundRemover,
    SimpleBackgroundRemover,
)


def create_copy_provider(name: str) -> CopyProvider:
    providers = {
        "mock": MockCopyProvider,
        "gpt-5.4-mini": lambda: OpenAICopyProvider("gpt-5.4-mini"),
        "gpt-5.4-nano": lambda: OpenAICopyProvider("gpt-5.4-nano"),
        "qwen3-8b": QwenCopyProvider,
    }
    if name not in providers:
        raise ValueError(f"unknown copy provider: {name}")
    return providers[name]()


def create_image_provider(name: str, quality: str = "medium") -> ImageProvider:
    providers = {
        "mock": MockImageProvider,
        "gpt-image-2": lambda: OpenAIImageProvider(
            quality=cast(Literal["low", "medium", "high"], quality)
        ),
        "flux2-klein-4b": FluxImageProvider,
    }
    if name not in providers:
        raise ValueError(f"unknown image provider: {name}")
    return providers[name]()


def create_background_remover(name: str) -> BackgroundRemover:
    providers = {
        "simple": SimpleBackgroundRemover,
        "birefnet": BiRefNetBackgroundRemover,
    }
    if name not in providers:
        raise ValueError(f"unknown background remover: {name}")
    return providers[name]()
