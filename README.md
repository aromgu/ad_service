# ad_service

멀티모달 생성형 AI 서비스. 자연어 + 이미지를 입력받아 자연어 + 이미지를 생성한다.

## 개요

- **입력**: 자연어 텍스트, 이미지 (둘 중 하나 또는 둘 다)
- **출력**: 자연어 텍스트, 이미지 (둘 중 하나 또는 둘 다)
- **핵심 모델**: 멀티모달 Vision-Language Model (VLM) + 이미지 생성 모델
- **서빙**: FastAPI
- **배포**: Docker (CPU / GPU 이미지 분리)

> 현재 상태: 디렉터리 / 파일 스캐폴딩만 구성됨. `.py` 파일은 전부 빈 파일이며 실제 구현은 아직 진행 전.
> Docker / 설정 / CI 파일만 내용이 채워져 있다.

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
│   ├── api/               # FastAPI 앱 (routes, schemas)
│   ├── core/              # 설정, 공통 상수
│   ├── models/            # VLM / 이미지 생성 모델 래퍼
│   ├── pipelines/         # 전처리 + 추론 파이프라인
│   ├── data/              # 데이터셋 / 로더
│   ├── prompts/           # 프롬프트 템플릿
│   ├── training/          # 학습 / 파인튜닝
│   └── utils/             # I/O, 이미지, 로깅 유틸
└── tests/                 # unit / integration 테스트
```

## 빠른 시작

```bash
# 로컬 개발 (venv)
make install
make run

# Docker (CPU API 서버)
docker compose -f docker/docker-compose.yml up api

# Docker (GPU)
docker build -f docker/Dockerfile.gpu -t ad-service:gpu .
```

## 환경 변수

`.env.example`를 `.env`로 복사해서 채운다.

```bash
cp .env.example .env
```

`docker run` 시 `--env-file .env`로 주입된다.

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
