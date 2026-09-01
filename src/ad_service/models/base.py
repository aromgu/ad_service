from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from ad_service.api.schemas.generation import CopyResult, GenerationRequest


@dataclass(slots=True)
class ProviderMetrics:
    latency_ms: int = 0
    estimated_cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CopyProviderOutput:
    value: CopyResult
    metrics: ProviderMetrics


@dataclass(slots=True)
class ImageProviderOutput:
    image: Image.Image
    metrics: ProviderMetrics


class CopyProvider(ABC):
    name: str

    @abstractmethod
    def generate(self, request: GenerationRequest) -> CopyProviderOutput:
        raise NotImplementedError


class ImageProvider(ABC):
    name: str

    @abstractmethod
    def generate_background(
        self,
        request: GenerationRequest,
        asset_type: str,
        width: int,
        height: int,
        prompt: str,
        seed: int,
    ) -> ImageProviderOutput:
        raise NotImplementedError


class BackgroundRemover(ABC):
    name: str

    @abstractmethod
    def remove(self, image_path: Path, bbox: tuple[int, int, int, int] | None) -> Image.Image:
        """Return an RGBA product cutout."""
        raise NotImplementedError
