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
    # 공급자가 원본 이미지를 직접 편집할 수 있는지 파이프라인이 호출 전에 확인합니다.
    supports_reference_edit: bool = False

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

    def edit_reference_image(
        self,
        request: GenerationRequest,
        image_path: Path,
        asset_type: str,
        width: int,
        height: int,
        prompt: str,
        seed: int,
    ) -> ImageProviderOutput:
        """원본 이미지를 참고해 완성 이미지를 직접 편집합니다.

        모든 이미지 모델이 편집 API를 제공하는 것은 아닙니다. 지원하지 않는 공급자는
        명확한 오류를 내고, 실제 구현을 가진 공급자만 이 메서드를 덮어씁니다.
        """

        del request, image_path, asset_type, width, height, prompt, seed
        raise RuntimeError(f"{self.name} does not support direct reference-image editing")


class BackgroundRemover(ABC):
    name: str

    def select_for_bbox(
        self,
        bbox: tuple[int, int, int, int] | None,
    ) -> "BackgroundRemover":
        """이번 요청에 실제로 사용할 배경 제거기를 반환합니다.

        보통의 제거기는 자기 자신을 그대로 사용합니다. 자동 라우터만 이 메서드를
        덮어써서 입력 박스 유무에 맞는 모델을 선택합니다.
        """

        del bbox
        return self

    @abstractmethod
    def remove(self, image_path: Path, bbox: tuple[int, int, int, int] | None) -> Image.Image:
        """Return an RGBA product cutout."""
        raise NotImplementedError
