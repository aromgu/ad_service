import json
from pathlib import Path

import pytest

from ad_service.cli import main

# 파일 위치를 기준으로 프로젝트 최상위 폴더를 찾습니다.
# 테스트를 어느 터미널 위치에서 실행해도 예제 JSON을 찾을 수 있게 하기 위함입니다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("request_file", "expected_mode", "expected_assets"),
    [
        ("text_only.json", "text_only", 1),
        ("image_only.json", "image_only", 1),
        ("text_and_image.json", "text_and_image", 2),
    ],
)
def test_cli_supports_all_input_modes(
    request_file: str,
    expected_mode: str,
    expected_assets: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """세 입력 방식이 Mock 모델을 사용해 결과 파일까지 만드는지 확인합니다."""

    monkeypatch.chdir(PROJECT_ROOT)
    request_path = PROJECT_ROOT / "examples" / "requests" / request_file
    output_path = tmp_path / expected_mode

    # 기본 공급자가 Mock이므로 API 키나 GPU, 실제 비용이 필요하지 않습니다.
    main(
        [
            "generate",
            "--input",
            str(request_path),
            "--output",
            str(output_path),
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == expected_mode
    assert len(result["assets"]) == expected_assets
    assert (output_path / result["request_id"] / "result.json").is_file()
