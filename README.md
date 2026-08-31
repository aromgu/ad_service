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

## 빠른 시작 (예정)

```bash
# 로컬 개발
make install
make run

# Docker (CPU)
docker compose -f docker/docker-compose.yml up api

# Docker (GPU)
docker build -f docker/Dockerfile.gpu -t ad-service:gpu .
```

## 환경 변수

`.env.example`를 `.env`로 복사해서 채운다.
