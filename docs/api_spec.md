# API 명세서 (v0.3 draft)

> 상태: **초안 / 팀 검토 대기.** 이 문서가 프론트엔드·모델·백엔드가 맞춰야 할 단일 계약(single source of truth)이다.
> D1~D11 결정은 서버/API 담당이 확정했다. D5·D9·D11 은 프론트(thlee)·모델(cjpark) 이 코드에 반영하며 확인한다.
>
> **구현 상태**: 이 명세대로 동작하는 FastAPI 골격(mock 파이프라인)이 별도 PR 로 올라가 있다.
> 엔드포인트·스키마·비동기 job·에러 엔벨로프 전부 동작하며, 실제 모델만 `MockPipeline` 자리에 끼우면 된다.

작성: 서버/API 담당 · 최초 2026-09-10

---

## 0. 배경 — 계약이 3갈래로 갈라져 있었음

| 위치 | 요청 형식 | 응답 형식 |
|---|---|---|
| `frontend/app.py` (thlee) | `store_name, business_type, target_audience, keywords, tone_manner` | `ad_text, image_url` |
| `backend/routers/ad.py` (thlee) | `category, product_name` | `status, message, generated_copy` |
| `src/ad_service/api/` (cjpark, `cjpark-model-baseline`) | `GenerationRequest` (request_id, text, image_path, outputs[], options{}) | `GenerationResult` (copy, assets[], metrics) |

**통합 방향**: cjpark 의 `GenerationRequest` / `GenerationResult` 스키마를 뼈대로 채택.
웹 서비스에 필요한 부분(이미지 드래그앤드롭 업로드, 결과 이미지 URL, request_id 서버 생성, **비동기 처리**)을 추가.
`backend/` 독립 FastAPI 앱은 `src/ad_service/api/` 로 흡수 (D11).

---

## 1. 공통 규약

| 항목 | 값 |
|---|---|
| Base URL (개발) | `http://localhost:8000` / 컨테이너 내부 `http://api:8000` |
| API prefix | `/api/v1` (D1) |
| 콘텐츠 타입 | 요청/응답 `application/json`, 이미지 포함 요청은 `multipart/form-data` |
| 문자셋 | UTF-8 |
| 인증 | MVP 없음. 배포 시 재검토 (D6) |
| 처리 방식 | **비동기** — 생성 요청은 즉시 접수(202)하고 결과는 폴링으로 조회 (D2) |
| 자동 문서 | `GET /docs` (Swagger UI), `GET /openapi.json` |

### 공통 에러 응답

모든 4xx / 5xx 는 아래 형태로 통일한다.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "사람이 읽을 수 있는 설명",
    "details": [
      { "field": "options.copy_style", "issue": "custom 선택 시 custom_instruction 필요" }
    ]
  }
}
```

| HTTP | code | 상황 |
|---|---|---|
| 400 | `BAD_REQUEST` | JSON 파싱 불가, multipart 형식 오류 |
| 404 | `NOT_FOUND` | 존재하지 않는 asset / request_id |
| 413 | `PAYLOAD_TOO_LARGE` | 이미지 용량 초과 (기본 10MB) |
| 422 | `VALIDATION_ERROR` | 스키마 검증 실패 (필드 조합 오류 포함) |
| 429 | `BUDGET_EXCEEDED` | 요청 비용이 예산 캡 초과 |
| 500 | `INTERNAL_ERROR` | 처리되지 않은 서버 오류 |
| 503 | `MODEL_UNAVAILABLE` | 추론 백엔드(모델 / Triton) 응답 불가 |

> 비동기 처리이므로, **생성 자체의 실패**(모델 오류 등)는 위 HTTP 에러가 아니라
> job 상태 `failed` + `error` 객체로 전달된다 (섹션 5 참조).

---

## 2. 엔드포인트 목록

| 메서드 | 경로 | 용도 |
|---|---|---|
| `GET` | `/health` | 헬스체크 (배포·모니터링용, prefix 없음) |
| `GET` | `/metrics` | Prometheus 메트릭 (`docs/monitoring.md`) |
| `POST` | `/api/v1/generate` | 광고 생성 **작업 접수** → `202` + `request_id` |
| `GET` | `/api/v1/jobs/{request_id}` | 작업 상태·결과 조회 (프론트가 폴링) |
| `GET` | `/api/v1/assets/{request_id}/{filename}` | 생성된 이미지 파일 반환 |

---

## 3. `GET /health`

배포 스크립트와 compose healthcheck 가 사용. 인증 없음, prefix 없음.

**200 OK**
```json
{ "status": "ok", "service": "ad_service", "version": "0.1.0" }
```

---

## 4. `POST /api/v1/generate` — 작업 접수

요청을 받아 **큐에 넣고 즉시 202 를 반환**한다. 실제 생성은 백그라운드에서 진행.

### 4.1 요청

- 이미지 없음: `Content-Type: application/json`, 본문은 아래 JSON.
- 이미지 있음 (드래그앤드롭): `Content-Type: multipart/form-data`
  - 파트 `payload` — 아래 JSON 을 문자열로
  - 파트 `image` — 이미지 파일 (jpg / png / webp, ≤ 10MB)

```jsonc
{
  // 없으면 서버가 생성해서 응답에 담아 돌려준다 (D7). 재시도 시 같은 값 재사용 권장.
  "request_id": "a1b2c3d4",

  // 제품/상황 설명. outputs 에 "copy" 가 있으면 필수. 최대 2000자 (D10).
  "text": "국산 딸기로 만든 300g 수제 딸기잼. 유리병 포장.",

  // 생성할 결과 종류. 1~4개, 중복 불가.
  // MVP 는 "copy", "banner" 만 실제 지원. "detail_visual", "product_image" 는 후속 (D5).
  "outputs": ["copy", "banner"],

  "options": {
    "store_name": "OO 카페",                          // 신규 (D4). 매장 상호명
    "business_type": "food_retail",                   // 현재 MVP 고정
    "product_category": "packaged_food",              // packaged_food | snack_beverage | side_dish_meal
    "sales_channel": "smart_store",                   // smart_store | social_media | delivery_app | offline_store
    "campaign_goal": "purchase_conversion",           // product_launch | promotion | brand_awareness | purchase_conversion
    "target_audience": "간편한 아침 식사를 준비하는 20~40대",
    "tone": "밝고 믿음직한",
    "copy_style": "informative",                      // emotional | informative | conversion | friendly | premium | custom
    "copy_length": "standard",                        // short | standard | detailed
    "use_emoji": false,
    "must_include": ["국산 딸기", "300g"],            // 최대 5개, 각 60자 이하
    "avoid_phrases": ["최고", "건강에 좋은"],          // 최대 10개
    "custom_instruction": null,                       // copy_style == "custom" 이면 필수
    "price": null,
    "offer": null
  },

  // 자유 메타데이터. 서버는 저장만 하고 해석하지 않음.
  "source": { "channel": "web" }
}
```

#### 필드 규칙

| 필드 | 타입 | 필수 | 비고 |
|---|---|---|---|
| `request_id` | string `^[a-zA-Z0-9_-]{1,80}$` | X | 생략 시 서버 생성 (D7) |
| `text` | string ≤ 2000자 | 조건부 | `outputs` 에 `copy` 포함 시 필수. 공백만 있으면 없는 것으로 처리 |
| `image` (multipart) | 파일 | X | jpg / png / webp, ≤ 10MB |
| `outputs` | `["copy"｜"banner"｜"detail_visual"｜"product_image"]` | O | 1~4개, 중복 불가 |
| `options.*` | 위 예시 참조 | X | 전부 기본값 있음 |

#### 검증 규칙 (422 발생 조건)

- `text` 와 `image` 가 둘 다 없음
- `outputs` 에 `copy` 가 있는데 `text` 없음
- `options.copy_style == "custom"` 인데 `custom_instruction` 없음
- `must_include` 와 `avoid_phrases` 에 같은 표현
- `outputs` 중복

### 4.2 응답

**202 Accepted**
```json
{
  "request_id": "a1b2c3d4",
  "status": "pending",
  "poll_url": "/api/v1/jobs/a1b2c3d4"
}
```

검증 실패 시에는 202 가 아니라 **422** + 공통 에러 응답.

---

## 5. `GET /api/v1/jobs/{request_id}` — 상태·결과 조회

프론트엔드가 접수 후 **2초 간격으로 폴링**한다. 작업 결과는 완료 후 24시간 보관.

### 진행 중

**200 OK**
```json
{ "request_id": "a1b2c3d4", "status": "processing", "progress": 0.4 }
```

`status`: `pending`(큐 대기) → `processing`(생성 중) → `done` / `failed`.
`progress` 는 0.0~1.0, 대략치 (없으면 생략 가능).

### 완료

**200 OK**
```jsonc
{
  "request_id": "a1b2c3d4",
  "status": "done",
  "result": {
    "mode": "text_only",                     // text_only | image_only | text_and_image

    // outputs 에 "copy" 가 있을 때만 존재
    "copy": {
      "product_summary": "국산 딸기를 담은 수제 딸기잼 300g",
      "headline_candidates": ["아침이 달라지는 국산 딸기잼", "...", "..."],  // 3개, 각 ≤ 25자
      "body_candidates": ["...", "...", "..."],                             // 3개, 각 ≤ 90자
      "cta_candidates": ["구매하기", "담기", "더보기"],                      // 3개, 각 ≤ 8자
      "keywords": ["국산 딸기", "수제잼", "300g"],
      "warnings": []
    },

    // 이미지 outputs 마다 1개
    "assets": [
      {
        "type": "banner",                    // banner | detail_visual | product_image
        "url": "/api/v1/assets/a1b2c3d4_banner.png",
        "width": 1536,
        "height": 1024,
        "model": "gpt-image-2",
        "seed": 12345,                       // 없을 수 있음 (null)
        "text_safe_area": { "x": 80, "y": 80, "width": 1376, "height": 300 },
        "latency_ms": 4200,
        "estimated_cost_usd": 0.02
      }
    ],

    "metrics": {
      "latency_ms": 8100,
      "estimated_cost_usd": 0.023,
      "copy_model": "gpt-5.4-mini",
      "image_model": "gpt-image-2"
    },

    "warnings": [],
    "errors": []
  }
}
```

- `copy` 는 `outputs` 에 `copy` 없으면 생략.
- `assets` 는 이미지 outputs 없으면 `[]`.
- 일부 output 만 실패하면 나머지는 그대로 주고 실패분은 `result.errors` 에 기록 (부분 성공 허용).

### 실패

**200 OK** (HTTP 자체는 성공, 작업이 실패한 것)
```json
{
  "request_id": "a1b2c3d4",
  "status": "failed",
  "error": { "code": "MODEL_UNAVAILABLE", "message": "이미지 모델 응답 없음 (timeout 120s)" }
}
```

### 없는 request_id

**404** + `{ "error": { "code": "NOT_FOUND", "message": "..." } }`
(보관 기간 24시간 지난 것도 404)

### 구현 메모

- 작업 상태 저장: MVP 는 서버 프로세스 메모리(dict). API 인스턴스 2개 이상 뜨면 Redis 로 교체.
- 백그라운드 실행: FastAPI `BackgroundTasks` 또는 `asyncio` 큐. 무거워지면 워커 분리(Celery/RQ).

---

## 6. `GET /api/v1/assets/{request_id}/{filename}`

job 결과의 `assets[].url` 이 가리키는 이미지 파일을 반환.

- 200: `image/png` (또는 jpg/webp) 바이너리
- 404: 존재하지 않는 asset
- `request_id` 는 `^[a-zA-Z0-9_-]{1,80}$`, `filename` 은 `^[a-zA-Z0-9_-]+\.(png|jpg|jpeg|webp)$` 만 허용 (경로 탈출 방지)
- 저장 위치: `data/outputs/api/{request_id}/{filename}` (설정 `AD_OUTPUT_ROOT`) — 서버 디스크 (D8). 추후 GCS.

---

## 7. 프론트엔드 필드 매핑 (thlee `frontend/app.py` 수정 필요)

### 요청 매핑

| 현재 프론트 필드 | 새 스펙 위치 | 변환 |
|---|---|---|
| `store_name` "OO 카페" | `options.store_name` | 그대로 |
| `business_type` "카페/디저트" | `options.business_type` + `options.product_category` | 한글 라벨 → enum 매핑표 필요 (D9) |
| `target_audience` | `options.target_audience` | 그대로 |
| `keywords` "수제 디저트, 분위기 좋은" | `options.must_include` | 쉼표 split → 배열 |
| `tone_manner` "친근하고 재치 있는" | `options.tone` + `options.copy_style` | 라벨 → enum 매핑 (D9) |
| (신규) | `text` | 제품 설명 입력란 추가. copy 생성에 필수 |
| (신규) | `outputs` | 결과 종류 선택 (기본 `["copy","banner"]`) |
| (드래그앤드롭) | multipart `image` 파트 | 파일 있으면 multipart, 없으면 순수 JSON |

### 호출 흐름 변경 (동기 → 비동기)

```python
# 1) 접수
res = requests.post("http://api:8000/api/v1/generate", json=payload)  # 또는 files=
request_id = res.json()["request_id"]

# 2) 폴링 (2초 간격)
while True:
    job = requests.get(f"http://api:8000/api/v1/jobs/{request_id}").json()
    if job["status"] in ("done", "failed"):
        break
    time.sleep(2)

# 3) 결과 사용
if job["status"] == "done":
    r = job["result"]
    headline = r["copy"]["headline_candidates"][0]
    img_url = "http://localhost:8000" + r["assets"][0]["url"]   # 브라우저에서 로드
```

Streamlit 은 `st.spinner` + 위 폴링 루프로 처리. (SSE/WebSocket 은 MVP 범위 밖)

---

## 8. 확정된 결정 (D1~D11)

| # | 안건 | 결정 | 검토자 |
|---|---|---|---|
| D1 | API prefix | **`/api/v1` 로 통일** (cjpark `/v1` → 변경) | 확정 |
| D2 | 동기 vs 비동기 | **비동기.** `generate` 202 접수 + `jobs/{id}` 폴링 | 확정 |
| D3 | 이미지 입력 방식 | **드래그앤드롭 → `generate` 에 multipart 단일 요청.** 별도 업로드 엔드포인트 없음 | 확정 |
| D4 | 매장 정보 필드 | `options.store_name` 신규 추가 | 확정 |
| D5 | MVP 지원 `outputs` | **`copy`, `banner` 우선.** `detail_visual`, `product_image` 후속 | cjpark 검토 |
| D6 | 인증 | MVP 없음. 배포 시 재검토 | 확정 |
| D7 | `request_id` 생성 | 클라이언트가 주면 사용, 없으면 **서버 생성** | 확정 |
| D8 | asset 저장소 | **로컬 디스크** + API 서빙. 추후 GCS | 확정 |
| D9 | 한글 라벨 → enum 매핑표 | **thlee 초안 → API 담당 확정** | thlee |
| D10 | `text` 최대 길이 | **2000자** (`app_config.yaml` 도 2000 으로 맞춤) | 확정 |
| D11 | `backend/` 폐기 | **완료.** `backend/` 삭제, `src/ad_service/api/` 로 단일화 | 확정 |

---

## 9. 예시 요청 모음

`examples/requests/` 에 실제 JSON 파일로 관리 (cjpark 브랜치에 시작됨).
프론트·백·모델이 모두 이 파일들로 테스트한다.

| 파일 | 시나리오 |
|---|---|
| `copy_only.json` | 텍스트만 → 문구만 |
| `copy_and_banner.json` | 텍스트만 → 문구 + 배너 |
| `image_text.json` | 텍스트 + 상품 사진 → 배너 |
| `validation_error.json` | 일부러 422 나는 요청 (테스트용) |

---

## 10. 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v0.1 | 2026-09-10 | 초안. 3갈래 계약 통합안, 결정 안건 D1~D11 도출 |
| v0.2 | 2026-09-10 | D1~D11 잠정 확정 반영. 비동기 처리(`jobs/{id}` 폴링) 로 구조 변경, `options.store_name` 추가, 프론트 호출 흐름 재작성 |
| v0.3 | 2026-09-10 | FastAPI 골격 구현과 함께 정리. 자산 URL 을 `/assets/{request_id}/{filename}` 2세그먼트로 확정 |
| v0.4 | 2026-09-10 | `backend/` 삭제 (D11 완료). compose 정리(healthcheck·depends_on·env_file 옵션), 프론트 `app.py` 비동기 대응, 모델 연결 가이드 추가 |
| v0.5 | 2026-09-10 | `/metrics` (Prometheus) 추가, 요청마다 `X-Request-ID` 응답 헤더 (없으면 서버 생성) |
