def test_factory_can_be_imported_directly() -> None:
    """모델 팩토리를 직접 불러와도 API 모듈과 순환 import가 발생하지 않아야 합니다."""

    from ad_service.factory import create_background_remover

    remover = create_background_remover("sam2")
    assert remover.name == "facebook/sam2.1-hiera-small"
