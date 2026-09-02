# ad_service

한국어 광고 문구와 원본 제품 보존형 광고 이미지를 생성하는 모델 베이스라인이다.

- 입력: 텍스트만, 이미지만, 또는 텍스트와 이미지 함께 사용
- 출력: 요청한 광고 문구, 배너, 상세 페이지 시각자료, 제품 이미지
- 원칙: 이미지 모델은 텍스트와 제품을 그리지 않고 배경만 생성한다. 실제 제품은 배경 제거 후
  원본 픽셀을 합성하며, 한글은 Pillow 또는 서비스의 HTML/Canvas에서 렌더링한다.
- 비교 모델: GPT-5.4 Mini/Nano, Qwen3-8B, GPT-Image-2, FLUX.2 Klein 4B
- 서빙: FastAPI `POST /v1/generate`

## 빠른 시작

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 1. 텍스트만 입력: 광고 문구와 배너 생성
ad-service generate \
  --input examples/requests/text_only.json \
  --output data/outputs/smoke_cli/text_only

# 2. 이미지만 입력: 제품 이미지 생성
ad-service generate \
  --input examples/requests/image_only.json \
  --output data/outputs/smoke_cli/image_only

# 3. 텍스트와 이미지 함께 입력: 문구·배너·상세 시각자료 생성
ad-service generate \
  --input examples/requests/text_and_image.json \
  --output data/outputs/smoke_cli/text_and_image
```

세 명령은 기본값인 Mock 모델을 사용하므로 API 키, GPU, 비용이 필요하지 않는다. 결과는 각
출력 폴더의 요청 ID 하위에 `result.json`과 이미지 파일로 저장된다.

### 브라우저에서 프롬프트 입력하기

```bash
uvicorn ad_service.api.main:app --host 127.0.0.1 --port 8000
```

서버를 실행한 뒤 브라우저에서 `http://127.0.0.1:8000/demo`를 연다. 식료품 상품 카테고리,
판매 채널, 광고 목적, 프롬프트와 대상 고객을 작성하고 필요한 산출물을 선택하면 문구와 이미지를
한 화면에서 확인할 수 있다. 기본 설정은 Mock 모델이므로 실제 프롬프트 품질 비교는 모델 연결
이후 진행한다.

### 현재 데이터 방침

이번 베이스라인에서는 별도 학습 데이터셋을 구축하거나 특정 상품 수를 고정하지 않는다.
`examples/requests/`의 텍스트만·이미지만·텍스트와 이미지 입력은 학습 데이터가 아니라 기능과
모델을 동일 조건에서 확인하는 스모크 테스트 사례다. AI Hub 변환 명령은 후속 검토를 위한 선택
도구로만 유지하며 현재 모델 비교의 선행 조건으로 사용하지 않는다.

### 실제 모델 실행

```bash
# OpenAI 키는 .env에만 저장한다.
export OPENAI_API_KEY="..."

# 문구 비교: 동일한 텍스트 요청을 사용하고 이미지 생성은 무료 mock으로 고정
ad-service generate --input examples/requests/copy_food_retail.json \
  --copy-provider gpt-5.4-mini --image-provider mock \
  --output data/outputs/text_gpt54mini

ad-service generate --input examples/requests/copy_food_retail.json \
  --copy-provider gpt-5.4-nano --image-provider mock \
  --output data/outputs/text_gpt54nano

# L4 로컬 모델
ad-service generate --input examples/requests/copy_food_retail.json \
  --copy-provider qwen3-8b --image-provider mock \
  --output data/outputs/text_qwen3

# 이미지 모델은 텍스트와 이미지 입력 예제로 각각 실행
ad-service generate --input examples/requests/text_and_image.json \
  --copy-provider mock --image-provider gpt-image-2 --remover birefnet \
  --quality medium --budget-cap 10 --output data/outputs/image_gpt2

ad-service generate --input examples/requests/text_and_image.json \
  --copy-provider mock --image-provider flux2-klein-4b --remover birefnet \
  --output data/outputs/image_flux2
```

각 출력 폴더의 `budget.json`이 누적 예상 비용을 기록한다. 다음 호출 예상 비용을 더했을 때
`--budget-cap`을 넘으면 실행 전에 중단한다. 팀 전체 $30 한도 중 베이스라인 기본 상한은 $10이다.

### 평가표

```bash
ad-service make-score-sheet \
  --results data/outputs \
  --output data/outputs/evaluation_scores.csv

# 박창준·황인홍이 1~5점으로 작성한 뒤 집계
ad-service aggregate-scores \
  --scores data/outputs/evaluation_scores.csv \
  --output data/outputs/model_summary.csv
```

제품 보존 점수 4점 미만 또는 허위 주장 결과는 자동 탈락한다. 자세한 실행 순서는
[`docs/model_baseline.md`](docs/model_baseline.md)를 참고한다.

## GPU Docker에서 실험하기

```bash
# 최초 1회 또는 의존성이 변경됐을 때 실행
docker build -f docker/Dockerfile.gpu -t ad-service:gpu .

# GPU 컨테이너 안에서 작업
docker run -it --rm --gpus all \
  -v "$PWD":/app -w /app \
  -v /home/data:/data \
  -v /home/data/hf-cache:/app/models/checkpoints \
  --env-file .env \
  ad-service:gpu bash
```

팀 공용 `/home/data`가 없는 환경에서는 본인 경로를 대신 연결한다. 예를 들어 `cjpark` 계정은
`/home/cjpark/data`를 `/data`에 연결한다. 모델 캐시는 Git에 넣지 않고 `/data` 또는 별도 캐시
볼륨에 저장한다.

## API

```bash
uvicorn ad_service.api.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health
curl -X POST http://localhost:8000/v1/generate \
  -H 'Content-Type: application/json' \
  --data @examples/requests/text_and_image.json
```

공급자는 환경 변수로 선택한다.

```text
AD_COPY_PROVIDER=mock|gpt-5.4-mini|gpt-5.4-nano|qwen3-8b
AD_IMAGE_PROVIDER=mock|gpt-image-2|flux2-klein-4b
AD_BACKGROUND_REMOVER=simple|birefnet
AD_BUDGET_CAP_USD=10
```

## 디렉터리 구조

```
ad_service/
├── .github/workflows/     # CI 파이프라인
├── configs/               # 모델 / 앱 설정 (yaml)
├── data/
│   ├── raw/               # 원본 데이터
│   ├── processed/         # 전처리된 데이터
│   ├── samples/           # 데모 / 테스트용 샘플
│   └── outputs/           # 생성 결과물
├── deploy/triton/         # NVIDIA Triton Inference Server 모델 저장소
├── docker/                # Dockerfile, docker-compose
├── docs/                  # 설계 문서
├── models/checkpoints/    # 학습/다운로드된 가중치 (git 미포함)
├── notebooks/             # 실험 노트북
├── scripts/               # 유틸리티 스크립트
├── src/ad_service/
│   ├── api/               # FastAPI 앱과 공통 요청·응답 스키마
│   ├── core/              # 설정, 공통 상수
│   ├── models/            # OpenAI / Qwen / FLUX 모델 래퍼
│   ├── pipelines/         # 배경 제거, 원본 합성, 추론 파이프라인
│   ├── data/              # 데이터셋 / 로더
│   ├── prompts/           # 프롬프트 템플릿
│   ├── training/          # 학습 / 파인튜닝
│   └── utils/             # I/O, 이미지, 로깅 유틸
└── tests/                 # unit / integration 테스트
```

## 테스트

```bash
make lint
make test
```

실험용 Colab 시작점은 [`notebooks/01_baseline.ipynb`](notebooks/01_baseline.ipynb)이다.
