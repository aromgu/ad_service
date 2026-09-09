from pathlib import Path

import pytest
from PIL import Image

from ad_service.factory import create_background_remover
from ad_service.models.base import BackgroundRemover
from ad_service.pipelines.preprocessing import AutoBackgroundRemover, Sam2BackgroundRemover


class StubBackgroundRemover(BackgroundRemover):
    """무거운 실제 모델을 받지 않고 자동 선택 규칙만 검사하기 위한 대역입니다."""

    def __init__(self, name: str) -> None:
        self.name = name

    def remove(self, image_path, bbox):
        del bbox
        return Image.open(image_path).convert("RGBA")


def test_factory_creates_sam2_remover() -> None:
    """CLI에서 sam2를 선택하면 올바른 배경 제거기가 만들어져야 합니다."""

    remover = create_background_remover("sam2")

    assert isinstance(remover, Sam2BackgroundRemover)
    assert remover.name == "facebook/sam2.1-hiera-small"


def test_factory_creates_auto_remover() -> None:
    """auto를 선택하면 자동 선택 제거기가 만들어져야 합니다."""

    remover = create_background_remover("auto")

    assert isinstance(remover, AutoBackgroundRemover)


def test_auto_remover_selects_model_from_bbox_presence() -> None:
    """박스가 있으면 SAM2, 없으면 BiRefNet 경로를 선택해야 합니다."""

    birefnet = StubBackgroundRemover("birefnet-stub")
    sam2 = StubBackgroundRemover("sam2-stub")
    remover = AutoBackgroundRemover(birefnet=birefnet, sam2=sam2)

    assert remover.select_for_bbox(None) is birefnet
    assert remover.select_for_bbox((10, 10, 90, 90)) is sam2


def test_sam2_requires_a_target_box(tmp_path: Path) -> None:
    """복잡한 사진에서 목표가 불명확한 실행을 막기 위해 박스를 필수로 검사합니다."""

    image_path = tmp_path / "shelf.jpg"
    Image.new("RGB", (100, 100), "white").save(image_path)

    with pytest.raises(ValueError, match="requires image_bbox"):
        Sam2BackgroundRemover().remove(image_path, None)
