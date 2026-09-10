from functools import lru_cache

from app.core.config import SHARED_IMAGE_DIR, settings
from app.generation.mock import MockProvider


def _sample_urls() -> list[str]:
    """web/images 의 생성 샘플 이미지를 목업 결과로 사용한다."""
    if not SHARED_IMAGE_DIR.is_dir():
        return []
    names = sorted(p.name for p in SHARED_IMAGE_DIR.glob("serum_gen*.png"))
    return [f"/static/images/{n}" for n in names]


@lru_cache
def get_provider() -> MockProvider:
    if settings.generation_provider != "mock":
        # RemoteProvider 는 Gu 의 추론 서버 스펙이 확정되면 추가한다.
        raise NotImplementedError(
            f"'{settings.generation_provider}' provider 는 아직 구현되지 않았습니다. "
            "GENERATION_PROVIDER=mock 으로 두세요."
        )
    return MockProvider(
        duration_seconds=settings.mock_duration_seconds,
        sample_urls=_sample_urls(),
    )
