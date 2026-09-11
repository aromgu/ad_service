# web/backend — 서비스 API

FastAPI + SQLAlchemy + SQLite. **모델 추론 서버(`src/ad_service`)와는 별개의 앱**이다.
이쪽은 회원·업로드·작업(job)·문서·목록처럼 서비스가 돌아가는 데 필요한 것만 담당하고,
실제 생성은 generation provider 뒤로 분리해 두었다.

## 실행

```bash
uv venv .venv
uv pip install -r requirements.txt --python .venv/bin/python
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

테스트:

```bash
.venv/bin/python -m pytest -q
```

- Swagger: <http://localhost:8000/docs>
- 정적 파일: `/static/uploads/*` (업로드 원본), `/static/images/*` (`web/web-images` 폴더를 서빙)

## 구조

```
app/
├── main.py              # 앱 조립, CORS, /static 마운트
├── core/config.py       # .env 설정 (pydantic-settings)
├── core/security.py     # bcrypt 해시 + JWT
├── db/models.py         # User, Asset, Job, Document, ChatMessage
├── schemas/common.py    # 요청/응답 스키마
├── api/deps.py          # 현재 사용자 (토큰 없으면 데모 계정)
├── api/routes/          # auth · uploads · jobs · documents · workspace · health
├── services/job_runner.py  # 생성 작업을 asyncio 태스크로 돌리며 진행률을 DB 에 기록
└── generation/          # ★ 생성 백엔드 교체 지점
    ├── base.py          #   GenerationProvider 프로토콜
    ├── mock.py          #   목업 구현 (현재 기본값)
    └── registry.py      #   GENERATION_PROVIDER 로 선택
```

## API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/api/health` | 상태 + 현재 provider |
| POST | `/api/auth/signup` | 회원가입 → 토큰 |
| POST | `/api/auth/login` | 로그인 → 토큰 |
| GET | `/api/auth/me` | 내 정보 |
| POST | `/api/uploads` | 이미지 업로드 (multipart, 최대 5장 / 10MB, PNG·JPG·WEBP) |
| POST | `/api/uploads/ai-edit` | AI 사진 편집 (3a-2). 프롬프트 + 장수 → 생성 이미지 |
| POST | `/api/jobs` | 생성 작업 시작 → `Job`. `type` 으로 세 플로우 분기 |
| GET | `/api/jobs/{id}` | 진행률·스텝 폴링 (`done` 이면 `document_id` 포함) |
| POST | `/api/jobs/{id}/cancel` | 생성 중단 |
| POST | `/api/jobs/{id}/retry` | 같은 입력값으로 재생성 (5a 의 "다시 시도"). 원본 작업은 남긴다 |
| GET | `/api/documents/{id}` | 문서 조회 |
| PATCH | `/api/documents/{id}` | 제목/섹션 저장 (에디터 자동 저장) |
| GET | `/api/documents/{id}/messages` | 채팅 스레드 |
| POST | `/api/documents/{id}/chat` | 채팅 수정 요청 → 응답 + 갱신된 문서 |
| GET | `/api/product-drafts/{id}` | 상품등록 정보 조회 (4c) |
| PATCH | `/api/product-drafts/{id}` | 검토 화면 수정 저장 |
| POST | `/api/product-drafts/{id}/register` | 네이버 등록 (연동 전 — 검증 + 상태 변경만) |
| GET | `/api/product-drafts/categories/search` | 카테고리 직접 검색 |
| GET·PUT | `/api/settings/shipping` | 배송 설정 (저장해 다음 등록에 재사용) |
| GET | `/api/workspace` | 내 작업 목록 (`?type=` 필터, 세 타입 모두) |
| DELETE | `/api/workspace/{job_id}` | 작업/문서/등록정보 삭제 |

## 작업 타입

| type | 결과물 | 스텝 |
| --- | --- | --- |
| `detail_page` | `Document` | 상품 정보 분석 → 카피 문구 작성 → 레이아웃 구성 → 이미지 배치 |
| `blog` | `Document` | 주제·키워드 분석 → 목차 구성 → 본문 작성 → 사진 배치 · 태그 추천 |
| `product_reg` | `ProductDraft` | 이미지 OCR 추출 → 브랜드·카테고리 분류 → 상품명·태그 생성 → 옵션·KC인증 판별 |

`product_reg` 는 `form.submit_mode` 가 `auto` 면 분석 직후 바로 등록 상태가 되고(4c 건너뜀),
`review` 면 `draft` 상태로 남아 4c 검토를 거친다.

## 실제 모델로 교체하려면

1. `app/generation/` 에 `remote.py` 를 만들고 `GenerationProvider` 프로토콜을 구현한다
   (`steps()`, `generate()`, `revise()`).
2. `registry.py` 의 분기에 `remote` 를 추가한다.
3. `.env` 에서 `GENERATION_PROVIDER=remote`, `REMOTE_GENERATION_URL=...` 로 바꾼다.

프론트엔드·DB·라우터는 전혀 손대지 않아도 된다.

## 알아 둘 제약

- `job_runner` 는 **단일 uvicorn 프로세스 전제**다. 워커를 늘리면(`-w N`) 태스크 레지스트리가
  프로세스별로 쪼개져 취소가 동작하지 않는다. 그 시점엔 Celery/RQ 같은 외부 큐로 옮겨야 한다.
- 스키마 마이그레이션 도구(Alembic)를 아직 안 붙였다. 기동 시 `create_all` 로 테이블만 만든다.
  모델을 바꾸면 `data/app.db` 를 지우고 다시 만드는 게 지금은 가장 빠르다.
- `ALLOW_DEMO_USER=true` 는 개발 편의용이다. 운영에서는 반드시 `false`.
- **"네이버에 상품 등록"은 항상 진짜 스토어에 상품을 만든다 (연습 모드 없음).**
  브라우저로 등록 흐름을 자동 테스트하지 말 것. pytest 는 `get_client` 를 가짜 클라이언트로
  바꿔 네이버를 부르지 않는다. 실수로 올라간 상품은
  `DELETE /v2/products/origin-products/{no}` 로 지울 수 있다.
- `.env` 는 기동할 때 한 번만 읽는다. 바꿨으면 백엔드를 재시작하거나
  `--reload --reload-include .env` 로 띄울 것.
- 사용자에게 보여줄 한국어 문구에 조사를 붙일 때는 `app/core/korean.py` 의 `eul_reul` 등을 쓴다.
  `f"{x}을(를)"` 같은 표기를 새로 만들지 말 것.
