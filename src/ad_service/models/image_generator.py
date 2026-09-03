from __future__ import annotations

import base64
import io
import os
import random
import time
from typing import Any, Literal

from PIL import Image, ImageDraw

from ad_service.api.schemas.generation import GenerationRequest
from ad_service.models.base import ImageProvider, ImageProviderOutput, ProviderMetrics

GPT_IMAGE_2_PRICES = {
    "low": {"1024x1024": 0.006, "1024x1536": 0.005, "1536x1024": 0.005},
    "medium": {"1024x1024": 0.053, "1024x1536": 0.041, "1536x1024": 0.041},
    "high": {"1024x1024": 0.211, "1024x1536": 0.165, "1536x1024": 0.165},
}


class MockImageProvider(ImageProvider):
    name = "mock-image-v1"

    def generate_background(
        self,
        request: GenerationRequest,
        asset_type: str,
        width: int,
        height: int,
        prompt: str,
        seed: int,
    ) -> ImageProviderOutput:
        rng = random.Random(f"{request.request_id}:{asset_type}:{seed}")
        base = tuple(rng.randint(218, 246) for _ in range(3))
        accent = tuple(max(0, channel - rng.randint(20, 45)) for channel in base)
        image = Image.new("RGB", (width, height), base)
        draw = ImageDraw.Draw(image, "RGBA")
        for index in range(7):
            radius = min(width, height) * (0.09 + index * 0.035)
            cx = width * (0.75 + rng.uniform(-0.14, 0.14))
            cy = height * (0.48 + rng.uniform(-0.22, 0.22))
            draw.ellipse(
                (cx - radius, cy - radius, cx + radius, cy + radius),
                fill=(*accent, max(8, 36 - index * 4)),
            )
        return ImageProviderOutput(image=image, metrics=ProviderMetrics(latency_ms=1))


class OpenAIImageProvider(ImageProvider):
    def __init__(
        self,
        model: str = "gpt-image-2",
        quality: Literal["low", "medium", "high"] = "medium",
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.name = model
        self.quality = quality
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAIImageProvider")

    def generate_background(
        self,
        request: GenerationRequest,
        asset_type: str,
        width: int,
        height: int,
        prompt: str,
        seed: int,
    ) -> ImageProviderOutput:
        del request, asset_type, seed
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("install runtime dependencies with `pip install -e .`") from exc
        started = time.perf_counter()
        response = OpenAI(api_key=self.api_key).images.generate(
            model=self.model,
            prompt=prompt,
            size=f"{width}x{height}",
            quality=self.quality,
            background="opaque",
        )
        data = response.data or []
        if not data:
            raise RuntimeError("OpenAI image response did not include image data")
        encoded = data[0].b64_json
        if not encoded:
            raise RuntimeError("OpenAI image response did not include b64_json")
        image = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGB")
        size_key = f"{width}x{height}"
        cost = GPT_IMAGE_2_PRICES.get(self.quality, {}).get(size_key, 0.0)
        return ImageProviderOutput(
            image=image,
            metrics=ProviderMetrics(
                latency_ms=int((time.perf_counter() - started) * 1000),
                estimated_cost_usd=cost,
            ),
        )


class FluxImageProvider(ImageProvider):
    name = "black-forest-labs/FLUX.2-klein-4B"

    def __init__(self, model_id: str = name) -> None:
        self.model_id = model_id
        self._pipe: Any = None
        self._load_latency_ms = 0
        self._model_vram_mb = 0.0

    def _load(self) -> None:
        if self._pipe is not None:
            return
        try:
            import torch
            from diffusers import Flux2KleinPipeline
        except ImportError as exc:
            raise RuntimeError("install ML dependencies with `pip install -e '.[ml]'`") from exc

        if not torch.cuda.is_available():
            raise RuntimeError("FLUX.2 [klein] 4B requires a CUDA GPU in this project")

        # 이 모델은 약 13GB VRAM을 사용합니다. 현재 실험 서버의 L4는 23GB이므로
        # 시스템 RAM으로 모델을 옮기지 않고 GPU에 직접 올려 더 안정적으로 실행합니다.
        load_started = time.perf_counter()
        torch.cuda.reset_peak_memory_stats()
        self._pipe = Flux2KleinPipeline.from_pretrained(
            self.model_id,
            torch_dtype=torch.bfloat16,
            device_map="cuda",
        )
        self._load_latency_ms = int((time.perf_counter() - load_started) * 1000)
        self._model_vram_mb = round(torch.cuda.memory_allocated() / 1024**2, 1)

    def generate_background(
        self,
        request: GenerationRequest,
        asset_type: str,
        width: int,
        height: int,
        prompt: str,
        seed: int,
    ) -> ImageProviderOutput:
        del request, asset_type
        self._load()
        import torch

        # 모델이 GPU에 적재된 상태에서 이미지 생성 중 최고 GPU 사용량을 측정합니다.
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        image = self._pipe(
            prompt=prompt,
            width=width,
            height=height,
            guidance_scale=1.0,
            num_inference_steps=4,
            generator=torch.Generator(device="cuda").manual_seed(seed),
        ).images[0]
        return ImageProviderOutput(
            image=image.convert("RGB"),
            metrics=ProviderMetrics(
                latency_ms=int((time.perf_counter() - started) * 1000),
                raw={
                    "load_latency_ms": self._load_latency_ms,
                    "model_vram_mb": self._model_vram_mb,
                    "peak_generation_vram_mb": round(
                        torch.cuda.max_memory_allocated() / 1024**2,
                        1,
                    ),
                    "device": "cuda",
                    "dtype": "bfloat16",
                    "num_inference_steps": 4,
                    "guidance_scale": 1.0,
                },
            ),
        )
