from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from ad_service.models.base import BackgroundRemover


def _crop_with_padding(
    image: Image.Image,
    bbox: tuple[int, int, int, int] | None,
    padding_ratio: float = 0.04,
) -> Image.Image:
    if bbox is None:
        return image.copy()
    xmin, ymin, xmax, ymax = bbox
    padding = int(max(xmax - xmin, ymax - ymin) * padding_ratio)
    box = (
        max(0, xmin - padding),
        max(0, ymin - padding),
        min(image.width, xmax + padding),
        min(image.height, ymax + padding),
    )
    return image.crop(box)


class SimpleBackgroundRemover(BackgroundRemover):
    """Offline fallback for studio-like samples; BiRefNet is preferred for final runs."""

    name = "simple-border-flood-v1"

    def __init__(self, threshold: float = 38.0, max_side: int = 1024) -> None:
        self.threshold = threshold
        self.max_side = max_side

    def remove(self, image_path: Path, bbox: tuple[int, int, int, int] | None) -> Image.Image:
        original = Image.open(image_path).convert("RGB")
        cropped = _crop_with_padding(original, bbox)
        working = cropped.copy()
        working.thumbnail((self.max_side, self.max_side), Image.Resampling.LANCZOS)
        pixels = np.asarray(working, dtype=np.float32)
        height, width = pixels.shape[:2]
        corner_samples = np.vstack(
            [
                pixels[: max(1, height // 20), : max(1, width // 20)].reshape(-1, 3),
                pixels[: max(1, height // 20), -max(1, width // 20) :].reshape(-1, 3),
                pixels[-max(1, height // 20) :, : max(1, width // 20)].reshape(-1, 3),
                pixels[-max(1, height // 20) :, -max(1, width // 20) :].reshape(-1, 3),
            ]
        )
        background = np.median(corner_samples, axis=0)
        candidate = np.linalg.norm(pixels - background, axis=2) <= self.threshold
        visited = np.zeros((height, width), dtype=bool)
        queue: deque[tuple[int, int]] = deque()
        for x in range(width):
            queue.append((0, x))
            queue.append((height - 1, x))
        for y in range(height):
            queue.append((y, 0))
            queue.append((y, width - 1))
        while queue:
            y, x = queue.popleft()
            if visited[y, x] or not candidate[y, x]:
                continue
            visited[y, x] = True
            if y > 0:
                queue.append((y - 1, x))
            if y + 1 < height:
                queue.append((y + 1, x))
            if x > 0:
                queue.append((y, x - 1))
            if x + 1 < width:
                queue.append((y, x + 1))
        alpha = Image.fromarray(np.where(visited, 0, 255).astype(np.uint8), mode="L")
        alpha = alpha.filter(ImageFilter.GaussianBlur(1.2))
        alpha = alpha.resize(cropped.size, Image.Resampling.LANCZOS)
        result = cropped.convert("RGBA")
        result.putalpha(alpha)
        return result


class BiRefNetBackgroundRemover(BackgroundRemover):
    name = "ZhengPeng7/BiRefNet"

    def __init__(self, model_id: str = name, resolution: int = 1024) -> None:
        self.model_id = model_id
        self.resolution = resolution
        self._model: Any = None
        self._transform: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from torchvision import transforms
            from transformers import AutoModelForImageSegmentation
        except ImportError as exc:
            raise RuntimeError("install ML dependencies with `pip install -e '.[ml]'`") from exc
        self._model = AutoModelForImageSegmentation.from_pretrained(
            self.model_id,
            trust_remote_code=True,
        ).eval()
        if torch.cuda.is_available():
            self._model = self._model.to("cuda")
        self._transform = transforms.Compose(
            [
                transforms.Resize((self.resolution, self.resolution)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )

    def remove(self, image_path: Path, bbox: tuple[int, int, int, int] | None) -> Image.Image:
        self._load()
        import torch

        image = _crop_with_padding(Image.open(image_path).convert("RGB"), bbox)
        tensor = self._transform(image).unsqueeze(0)
        device = next(self._model.parameters()).device
        with torch.no_grad():
            prediction = self._model(tensor.to(device))[-1].sigmoid().cpu()[0].squeeze()
        alpha = Image.fromarray((prediction.numpy() * 255).astype(np.uint8), mode="L")
        alpha = alpha.resize(image.size, Image.Resampling.LANCZOS)
        result = image.convert("RGBA")
        result.putalpha(alpha)
        return result
