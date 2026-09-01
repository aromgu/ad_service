# ad_service

한국어 광고 문구와 원본 제품 보존형 광고 이미지를 생성하는 모델 베이스라인이다.

- 입력: 상품명, 카테고리, 특징, 타깃, 톤, 가격·혜택, 제품 이미지
- 출력: 광고 문구 후보 3개, 배너, 상세 페이지 시각자료, 제품 이미지
- 원칙: 이미지 모델은 텍스트와 제품을 그리지 않고 배경만 생성한다. 실제 제품은 배경 제거 후
  원본 픽셀을 합성하며, 한글은 Pillow 또는 서비스의 HTML/Canvas에서 렌더링한다.
- 비교 모델: GPT-5.4 Mini/Nano, Qwen3-8B, GPT-Image-2, FLUX.2 Klein 4B
- 서빙: FastAPI `POST /v1/generate`

## 빠른 시작

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# API 키와 GPU 없이 전체 흐름 검증
ad-service generate \
  --input data/processed/eval_v1/requests/snack_001.json \
  --copy-provider mock \
  --image-provider mock \
  --remover simple \
  --output data/outputs/mock
```

### 평가 데이터 준비

```bash
ad-service prepare-data \
  --zip /path/to/이미지.zip \
  --output data/processed/eval_v1
```

ZIP에서 상품 7종의 `0도 단품` 이미지 한 장씩을 선택한다. 이용 조건 확인 전에는 내부 평가에만
사용하고 Git에 포함하지 않는다.

### 실제 모델 실행

```bash
# OpenAI 키는 .env에만 저장한다.
export OPENAI_API_KEY="..."

# 문구 비교: 이미지 생성은 무료 mock으로 고정
ad-service batch --manifest data/processed/eval_v1/requests.json \
  --copy-provider gpt-5.4-mini --image-provider mock \
  --output data/outputs/text_gpt54mini

ad-service batch --manifest data/processed/eval_v1/requests.json \
  --copy-provider gpt-5.4-nano --image-provider mock \
  --output data/outputs/text_gpt54nano

# API 이미지 21장: 7상품 × 3규격
ad-service batch --manifest data/processed/eval_v1/requests.json \
  --copy-provider mock --image-provider gpt-image-2 --remover birefnet \
  --quality medium --budget-cap 10 --output data/outputs/image_gpt2

# L4 로컬 모델
ad-service batch --manifest data/processed/eval_v1/requests.json \
  --copy-provider qwen3-8b --image-provider mock \
  --output data/outputs/text_qwen3

ad-service batch --manifest data/processed/eval_v1/requests.json \
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

## API

```bash
uvicorn ad_service.api.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health
curl -X POST http://localhost:8000/v1/generate \
  -H 'Content-Type: application/json' \
  --data @data/processed/eval_v1/requests/snack_001.json
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
