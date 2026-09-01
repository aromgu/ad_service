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

## Docker 환경에서 실험하기

VLM / 이미지 생성 / 학습 실험은 GPU 이미지(`ad-service:gpu`) 안에서 돌린다.
이 이미지에는 `torch` (CUDA 12.1), `transformers`, `diffusers`, `accelerate` 와
프로젝트 소스(`src/ad_service`)가 설치돼 있다.

### 0. 사전 준비 (VM에서 최초 1회, 관리자 권한 필요)

```bash
# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER    # 이후 재로그인

# NVIDIA Container Toolkit (컨테이너에서 GPU 사용)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

확인:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi -L
```

### 1. GPU 이미지 빌드 (최초 1회, 코드/의존성 바뀌면 다시)

```bash
docker build -f docker/Dockerfile.gpu -t ad-service:gpu .
```

### 2. 실험 코드 실행

레포와 공용 데이터 경로를 컨테이너에 마운트한다.
호스트에서 코드를 고치면 컨테이너 안에서 바로 반영된다 (`-v` 바인드 마운트).

```bash
# 스크립트 하나 실행
docker run --rm --gpus all \
  -v "$PWD":/app -w /app \
  -v /home/data:/data \
  --env-file .env \
  ad-service:gpu \
  python scripts/train.py            # 예시

# 인터랙티브 셸로 들어가서 작업
docker run -it --rm --gpus all \
  -v "$PWD":/app -w /app \
  -v /home/data:/data \
  --env-file .env \
  ad-service:gpu bash
```

### 3. GPU 인식 확인 (컨테이너 안에서)

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

### 옵션 정리

| 옵션 | 의미 |
|---|---|
| `--gpus all` | 호스트 GPU 전체를 컨테이너에 노출 |
| `-v "$PWD":/app` | 현재 레포를 `/app`에 마운트 (코드 즉시 반영) |
| `-v /home/data:/data` | 공용 데이터셋 경로 마운트 (아래 참고) |
| `--env-file .env` | 환경 변수 주입 |
| `--rm` | 종료 시 컨테이너 삭제 |
| `-it` | 인터랙티브 터미널 (셸 진입용) |

### Hugging Face 캐시 재사용 (선택)

모델 다운로드를 매번 반복하지 않으려면 캐시 디렉터리를 공용 경로에 두고 마운트한다.

```bash
docker run --rm --gpus all \
  -v "$PWD":/app -w /app \
  -v /home/data:/data \
  -v /home/data/hf-cache:/app/models/checkpoints \
  --env-file .env \
  ad-service:gpu python scripts/download_models.py
```

(`Dockerfile.gpu`에서 `HF_HOME=/app/models/checkpoints` 로 설정돼 있음)

---

## 공용 데이터 경로 (`/home/data`)

팀원들이 데이터셋을 각자 받아서 학습을 돌리는 **공유 작업 공간**이다.
VM의 모든 팀원이 읽고 쓸 수 있도록 그룹 권한이 걸려 있다.

```
/home/data/
├── <dataset_name>/       # 데이터셋별 디렉터리 (각자 받은 원본)
├── hf-cache/             # Hugging Face 모델 캐시 (공용, 선택)
└── runs/                 # 학습 산출물 / 체크포인트 (사용자별 하위 폴더 권장)
    ├── argu/
    ├── bhs33/
    └── ...
```

### 규칙

- **레포에 커밋하지 않는다.** 데이터/체크포인트는 전부 `/home/data` 아래에 둔다.
  (레포 안 `data/`, `models/checkpoints/` 는 `.gitignore` 처리돼 있음)
- 학습 산출물은 `/home/data/runs/<본인_아이디>/` 아래에 쓴다. 서로 덮어쓰지 않도록.
- 대용량 원본은 중복 다운로드하지 말고 `/home/data/<dataset_name>/` 을 공유한다.
- 컨테이너 안에서는 `/data` 로 접근한다 (`-v /home/data:/data`).

### 공용 경로 권한 설정 (관리자, 최초 1회)

```bash
sudo groupadd -f devteam
# 팀원 계정을 그룹에 추가
for u in argu bhs33 ChanwoolLee trium ahrom apple; do sudo usermod -aG devteam $u; done

sudo mkdir -p /home/data
sudo chgrp -R devteam /home/data
sudo chmod -R 2775 /home/data          # setgid: 새 파일도 그룹 상속
sudo setfacl -R -d -m g:devteam:rwx /home/data   # 기본 ACL (신규 파일 그룹 쓰기)
```

팀원은 그룹 반영을 위해 재로그인 후 `groups` 로 `devteam` 확인.
