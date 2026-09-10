# 모델 연결 가이드 (MockPipeline → 실제 모델)

대상: 모델 담당 (cjpark). API 계층은 이미 완성돼 있고, 파이프라인 한 곳만 구현하면 된다.

## 끼우는 지점

`src/ad_service/api/pipeline.py` 의 프로토콜:

```python
class GenerationPipeline(Protocol):
    def generate(self, data: GenerationInput, output_dir: Path) -> GenerationResult: ...
```

- `data.request` : 검증 끝난 `GenerationRequest` (text, outputs, options)
- `data.image_path` : 업로드된 입력 이미지 경로 (없으면 None)
- `data.mode` : `text_only` / `image_only` / `text_and_image`
- `output_dir` : 이 요청의 결과 이미지를 저장할 디렉터리 (`data/outputs/api/{request_id}/`)
- 반환 `GenerationResult` : `copy`(CopyResult) + `assets`(GeneratedAsset 목록) + `metrics`

`GeneratedAsset.url` 은 비워두면 job 러너가 `/api/v1/assets/{request_id}/{filename}` 로 채운다.
파일명은 `banner.png` 처럼 output 종류에 맞춰 저장하면 된다.

## 등록

`pipeline.py` 의 `build_pipeline()` 에 분기를 추가한다:

```python
def build_pipeline(copy_provider: str, image_provider: str) -> GenerationPipeline:
    if copy_provider == "mock" and image_provider == "mock":
        return MockPipeline()
    if copy_provider == "openai":
        from ad_service.pipelines.inference import RealPipeline
        return RealPipeline(...)
    ...
```

공급자 값은 `AD_COPY_PROVIDER` / `AD_IMAGE_PROVIDER` 환경변수 (`core/config.py`).

## 참고

- `cjpark-model-baseline` 브랜치에 이미 `GenerationRequest`/`GenerationResult` 와 거의 같은 구조,
  `pipelines/inference.py`, `factory.py`, provider 추상화가 있다. 그걸 이 프로토콜에 맞춰 옮기면 된다.
- 실제 추론은 GPU 가 필요하므로 `api` (CPU) 가 아니라 `api-gpu` 서비스 또는 Triton 뒤에 둔다.
  API 계층 코드는 그대로 두고 파이프라인만 원격 호출로 바꾸면 된다.
- 계약 스펙: `docs/api_spec.md`
