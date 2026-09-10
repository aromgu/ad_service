# ad_service

멀티모달 생성형 AI 서비스. 자연어 + 이미지를 입력받아 자연어 + 이미지를 생성한다.

## 개요

- **입력**: 자연어 텍스트, 이미지 (둘 중 하나 또는 둘 다)
- **출력**: 자연어 텍스트, 이미지 (둘 중 하나 또는 둘 다)
- **핵심 모델**: 멀티모달 Vision-Language Model (VLM) + 이미지 생성 모델
- **서빙**: FastAPI (비동기 job + 폴링)
- **배포**: Docker Compose (CPU / GPU 이미지 분리)

### 현재 상태

| 영역 | 상태 |
|---|---|
| API 서버 | 구현됨 — 엔드포인트·스키마·비동기 job·에러 규격·`/metrics` 동작. 생성은 `MockPipeline`(가짜) |
| 실제 모델 (VLM / 이미지 생성) | 작업 중 — `src/ad_service/api/pipeline.py` 프로토콜에 연결 ([docs/model_integration.md](docs/model_integration.md)) |
| 프론트엔드 (Streamlit) | 작업 중 — `frontend/` |
| CI | 동작 — lint·format·mypy·test·compose 검증·이미지 빌드 |
| 배포 | 수동 (`./scripts/deploy.sh`). 자동 배포는 개발 단계 지나면 |

## 디렉터리 구조

```
ad_service/
├── .github/workflows/     # CI (ci.yml) · 배포 (deploy.yml, 비활성)
├── configs/               # 모델 / 앱 설정 (yaml)
├── data/                  # raw / processed / samples / outputs
├── deploy/
│   ├── triton/            # NVIDIA Triton 모델 저장소
│   └── monitoring/        # Prometheus / Grafana 설정
├── docker/                # Dockerfile(CPU) · Dockerfile.gpu · docker-compose.yml
├── docs/                  # 아래 "문서" 참고
├── examples/requests/     # API 예시 요청 JSON
├── frontend/              # Streamlit 앱 (thlee)
├── models/checkpoints/    # 가중치 (git 미포함)
├── scripts/               # deploy.sh, download_models.py, ...
├── src/ad_service/
│   ├── api/               # FastAPI: routes, schemas, jobs, pipeline, metrics, observability
│   ├── core/              # 설정 (pydantic-settings)
│   ├── models/            # VLM / 이미지 생성 래퍼 (cjpark)
│   ├── pipelines/         # 전처리 + 추론 (cjpark)
│   └── prompts/, data/, training/, utils/
└── tests/                 # unit / integration (21)
```

## 빠른 시작

```bash
# API + 프론트 스택 (권장)
docker compose -f docker/docker-compose.yml up -d --build api frontend
#   API   http://localhost:8000/docs
#   front http://localhost:8501

# API만 로컬에서 (venv)
make install && make run
```

`.env` 는 없어도 뜬다. 값을 바꾸려면 `cp .env.example .env` 후 수정
(compose 는 있으면 읽고 `AD_*` 는 서비스에서 기본값 지정).

## 문서

| | |
|---|---|
| [docs/api_spec.md](docs/api_spec.md) | API 계약 (요청/응답 스키마, 에러 규격, 결정 D1~D11) |
| [docs/model_integration.md](docs/model_integration.md) | 실제 모델을 `MockPipeline` 자리에 연결하는 법 |
| [docs/monitoring.md](docs/monitoring.md) | `/metrics`, 로그, Prometheus/Grafana, 알림 |
| [docs/runbook.md](docs/runbook.md) | 장애 대응 |
| [docs/deployment.md](docs/deployment.md) | 배포 절차 · 롤백 · runner (나중) |

## API

전체 계약은 [docs/api_spec.md](docs/api_spec.md), 예시 요청은 `examples/requests/`.

| 메서드 | 경로 | |
|---|---|---|
| `POST` | `/api/v1/generate` | 생성 작업 접수 → `202 { request_id, poll_url }`. JSON 또는 이미지 포함 시 multipart |
| `GET` | `/api/v1/jobs/{request_id}` | 작업 상태·결과 (2초 폴링) |
| `GET` | `/api/v1/assets/{request_id}/{filename}` | 생성 이미지 |
| `GET` | `/health` · `/metrics` | 헬스체크 · Prometheus |

생성은 현재 `MockPipeline`(가짜 결과). 실제 모델 연결은 [docs/model_integration.md](docs/model_integration.md).

---

## Docker로 실험하기

VM에 Docker · GPU · 공용 데이터 경로(`/home/data`)는 이미 세팅돼 있다.
아래 명령어만 따라 하면 된다.

### 1. 이미지 빌드 (최초 1회, 의존성 바뀌면 다시)

```bash
docker build -f docker/Dockerfile.gpu -t ad-service:gpu .
```

`torch`(CUDA) · `transformers` · `diffusers` · `accelerate` 와 프로젝트 소스가 들어있다.

### 2. 환경 변수 파일

```bash
cp .env.example .env    # 필요한 값 채우기
```

### 3. 실험 코드 실행

```bash
# 스크립트 실행
docker run --rm --gpus all \
  -v "$PWD":/app -w /app \
  -v /home/data:/data \
  --env-file .env \
  ad-service:gpu \
  python scripts/train.py

# 컨테이너 셸로 들어가서 작업
docker run -it --rm --gpus all \
  -v "$PWD":/app -w /app \
  -v /home/data:/data \
  --env-file .env \
  ad-service:gpu bash
```

- `-v "$PWD":/app` — 레포 마운트. 호스트에서 코드 수정하면 컨테이너에 바로 반영.
- `-v /home/data:/data` — 공용 데이터 경로. 컨테이너 안에서는 `/data`.
- GPU 확인: `python -c "import torch; print(torch.cuda.is_available())"`

---

## 공용 데이터 경로 (`/home/data`)

팀원 모두가 읽고 쓸 수 있는 공유 작업 공간. 데이터셋을 각자 받아서 학습을 돌린다.

```
/home/data/
├── <dataset_name>/   # 데이터셋 원본 (한 번 받으면 공유)
├── hf-cache/         # Hugging Face 모델 캐시 (공용)
└── runs/<본인_아이디>/  # 학습 산출물 / 체크포인트
```

- 데이터 · 체크포인트는 레포에 커밋하지 않는다. 전부 `/home/data` 아래에 둔다.
- 학습 산출물은 `runs/<본인_아이디>/` 아래에 써서 서로 안 겹치게 한다.
- 대용량 원본은 중복 다운로드 말고 `/home/data/<dataset_name>/` 를 같이 쓴다.
- HF 캐시 공유: 컨테이너 실행 시 `-v /home/data/hf-cache:/app/models/checkpoints` 추가.
