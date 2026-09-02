"""Qwen 실험 전에 GPU와 필수 라이브러리를 확인하는 작은 도구입니다.

이 파일은 모델을 다운로드하거나 GPU 설정을 바꾸지 않습니다. 현재 Docker 안에서
PyTorch가 GPU를 찾을 수 있는지만 읽어서 보여주므로 실제 모델 실행 전에 안전하게
사용할 수 있습니다.
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    """환경 정보를 JSON으로 출력하고, GPU가 없으면 실패 코드로 종료합니다."""

    try:
        import torch
    except ImportError:
        # 초보자도 무엇을 설치해야 하는지 바로 알 수 있도록 원인을 짧게 출력합니다.
        print(
            json.dumps(
                {
                    "ready": False,
                    "error": "PyTorch가 설치되지 않았습니다.",
                    "next": "GPU Docker 이미지를 빌드한 뒤 이 파일을 다시 실행하세요.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)

    cuda_available = torch.cuda.is_available()
    result: dict[str, object] = {
        "ready": cuda_available,
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "cuda_available": cuda_available,
        "cuda_runtime": torch.version.cuda,
        "gpu_count": torch.cuda.device_count() if cuda_available else 0,
    }

    if cuda_available:
        # 첫 번째 GPU가 이번 단일 모델 스모크 테스트에 사용될 GPU입니다.
        result["gpu_name"] = torch.cuda.get_device_name(0)
        properties = torch.cuda.get_device_properties(0)
        result["gpu_memory_gb"] = round(properties.total_memory / (1024**3), 2)
        result["next"] = "환경 확인 완료: Qwen 문구 생성 테스트를 실행하세요."
    else:
        result["next"] = "Docker 실행 시 --gpus all 옵션과 NVIDIA 드라이버를 확인하세요."

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not cuda_available:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
