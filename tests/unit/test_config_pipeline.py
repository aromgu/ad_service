"""설정 파싱과 파이프라인 팩토리."""

from __future__ import annotations

import pytest

from ad_service.api.pipeline import MockPipeline, build_pipeline
from ad_service.core.config import Settings


def test_cors_origins_splits_comma() -> None:
    s = Settings(cors_allow_origins="http://a.com, http://b.com ,")
    assert s.cors_origins == ["http://a.com", "http://b.com"]


def test_cors_origins_default_is_wildcard() -> None:
    assert Settings().cors_origins == ["*"]


def test_build_pipeline_mock() -> None:
    assert isinstance(build_pipeline("mock", "mock"), MockPipeline)


def test_build_pipeline_unknown_provider_raises() -> None:
    with pytest.raises(NotImplementedError, match="model_integration"):
        build_pipeline("openai", "mock")
