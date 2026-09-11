from PIL import Image, ImageDraw, ImageFont

from ad_service.utils.image_utils import _wrap


def test_wrap_splits_an_oversized_first_word() -> None:
    draw = ImageDraw.Draw(Image.new("RGB", (200, 200), "white"))
    font = ImageFont.load_default(size=30)
    word = "abcdefghijklmnopqrstuv"
    lines = _wrap(draw, word, font, 100)
    assert "".join(lines) == word
    assert len(lines) > 1
    assert all(draw.textbbox((0, 0), line, font=font)[2] <= 100 for line in lines)


def test_wrap_keeps_normal_words_together() -> None:
    """줄 너비가 부족해도 한 단어의 중간에서 줄을 바꾸면 안 됩니다."""

    image = Image.new("RGB", (800, 200), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)
    text = "Blueberry snack sticks"
    width_before_last_word = draw.textbbox((0, 0), "Blueberry snack st", font=font)[2]

    lines = _wrap(draw, text, font, width_before_last_word)

    assert lines == ["Blueberry snack", "sticks"]
