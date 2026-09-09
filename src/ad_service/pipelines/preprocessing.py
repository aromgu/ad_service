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
        model_parameter = next(self._model.parameters())
        device = model_parameter.device

        # BiRefNet 가중치는 환경에 따라 float16 또는 float32로 로드될 수 있습니다.
        # 입력 이미지도 모델과 같은 자료형으로 바꿔야 합성곱 연산의 자료형 오류가 나지 않습니다.
        tensor = tensor.to(device=device, dtype=model_parameter.dtype)
        with torch.no_grad():
            prediction = self._model(tensor)[-1].sigmoid().cpu()[0].squeeze()
        alpha = Image.fromarray((prediction.numpy() * 255).astype(np.uint8), mode="L")
        alpha = alpha.resize(image.size, Image.Resampling.LANCZOS)
        result = image.convert("RGBA")
        result.putalpha(alpha)
        return result


class Sam2BackgroundRemover(BackgroundRemover):
    """박스로 지정한 물체 하나를 SAM2.1로 분리합니다.

    BiRefNet은 사진에서 가장 눈에 띄는 전경 전체를 찾는 데 강하지만, 매대처럼 같은 상품이
    서로 붙어 있으면 여러 물체를 함께 선택할 수 있습니다. SAM2는 사용자가 지정한 박스를
    모델의 입력 힌트로 사용하므로 이런 복잡한 사진에서 목표 상품 하나를 고르는 데 적합합니다.
    """

    name = "facebook/sam2.1-hiera-small"

    def __init__(self, model_id: str = name) -> None:
        self.model_id = model_id
        self._model: Any = None
        self._processor: Any = None
        self._device = "cpu"

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import Sam2Model, Sam2Processor
        except ImportError as exc:
            raise RuntimeError("install ML dependencies with `pip install -e '.[ml]'`") from exc

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._processor = Sam2Processor.from_pretrained(self.model_id)
        self._model = Sam2Model.from_pretrained(self.model_id).eval().to(self._device)

    def remove(self, image_path: Path, bbox: tuple[int, int, int, int] | None) -> Image.Image:
        # SAM2는 어떤 물체를 선택할지 알려 주는 박스가 꼭 필요합니다.
        if bbox is None:
            raise ValueError("SAM2 background removal requires image_bbox")

        self._load()
        import torch

        image = Image.open(image_path).convert("RGB")
        xmin, ymin, xmax, ymax = bbox

        # 사진 범위를 벗어난 좌표가 모델에 들어가지 않도록 안전하게 보정합니다.
        prompt_box = [
            max(0, min(xmin, image.width - 1)),
            max(0, min(ymin, image.height - 1)),
            max(1, min(xmax, image.width)),
            max(1, min(ymax, image.height)),
        ]
        if prompt_box[2] <= prompt_box[0] or prompt_box[3] <= prompt_box[1]:
            raise ValueError("image_bbox must overlap the input image")

        # 바깥쪽 두 겹은 사진과 물체 목록, 안쪽 배열은 한 물체의 박스 좌표입니다.
        inputs = self._processor(
            images=image,
            input_boxes=[[prompt_box]],
            return_tensors="pt",
        ).to(self._device)
        with torch.no_grad():
            outputs = self._model(**inputs)

        # SAM2는 후보 마스크 3개와 각 후보의 예상 품질 점수를 반환합니다.
        # 가장 높은 점수의 마스크만 골라 투명도(alpha)로 사용합니다.
        original_sizes = inputs["original_sizes"].cpu()
        masks = self._processor.post_process_masks(
            outputs.pred_masks.cpu(),
            original_sizes,
        )[0]
        scores = outputs.iou_scores.detach().cpu()[0, 0]
        best_mask_index = int(torch.argmax(scores).item())
        best_mask = masks[0, best_mask_index].to(dtype=torch.float32).numpy()

        alpha = Image.fromarray((best_mask * 255).astype(np.uint8), mode="L")
        alpha = alpha.filter(ImageFilter.GaussianBlur(0.8))
        result = image.convert("RGBA")
        result.putalpha(alpha)

        # 기존 합성기가 다루기 편하도록 목표 박스 주변만 잘라서 반환합니다.
        return _crop_with_padding(result, bbox)


class AutoBackgroundRemover(BackgroundRemover):
    """입력에 선택 박스가 있는지 보고 배경 제거 모델을 자동으로 고릅니다.

    박스가 없으면 사진의 주요 전경 전체를 찾는 BiRefNet을 사용합니다. 박스가 있으면
    복잡한 매대에서도 목표 상품 하나를 지정할 수 있는 SAM2를 사용합니다. 직접 편집은
    배경 제거 단계 자체를 건너뛰므로 이 클래스에서 선택하지 않습니다.
    """

    name = "auto"

    def __init__(
        self,
        birefnet: BackgroundRemover | None = None,
        sam2: BackgroundRemover | None = None,
    ) -> None:
        # 테스트에서는 가벼운 가짜 제거기를 넣을 수 있고, 실제 실행에서는 필요한 모델만
        # 나중에 로드됩니다. 따라서 두 모델을 만들어도 GPU 메모리를 미리 사용하지 않습니다.
        self.birefnet = birefnet or BiRefNetBackgroundRemover()
        self.sam2 = sam2 or Sam2BackgroundRemover()

    def select_for_bbox(
        self,
        bbox: tuple[int, int, int, int] | None,
    ) -> BackgroundRemover:
        """선택 박스가 있으면 SAM2, 없으면 BiRefNet을 반환합니다."""

        return self.sam2 if bbox is not None else self.birefnet

    def remove(self, image_path: Path, bbox: tuple[int, int, int, int] | None) -> Image.Image:
        """파이프라인 밖에서 직접 호출해도 같은 자동 규칙을 적용합니다."""

        return self.select_for_bbox(bbox).remove(image_path, bbox)
