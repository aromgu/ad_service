# API 명세서 (v0.1 draft)

> 상태: **초안 / 팀 확정 대기.** 이 문서가 프론트엔드·모델·백엔드가 맞춰야 할 단일 계약(single source of truth)이다.
> 확정 전까지 각자 구현은 이 문서를 기준으로 하고, 바꿔야 할 부분은 아래 "확정이 필요한 결정" 섹션에 코멘트로 남긴다.

작성: 서버/API 담당 · 최초 2026-09-10

---

## 0. 배경 — 지금 계약이 3갈래로 갈라져 있음

| 위치 | 요청 형식 | 응답 형식 | 문제 |
|---|---|---|---|
| `frontend/app.py` (thlee) | `store_name, business_type, target_audience, keywords, tone_manner` | `ad_text, image_url` | 플랫 구조, 브라우저 폼 기준 |
| `backend/routers/ad.py` (thlee) | `category, product_name` | `status, message, generated_copy` | 프론트와 필드 불일치 |
| `src/ad_service/api/` (cjpark, `cjpark-model-baseline` 브랜치) | `GenerationRequest` (request_id, text, image_path, outputs[], options{}) | `GenerationResult` (copy, assets[], metrics) | 가장 정교함. 단 서버 파일경로 기반이라 웹 업로드/URL 흐름이 없음 |

**이 문서의 방향**: cjpark의 `GenerationRequest` / `GenerationResult` 스키마를 뼈대로 채택하되,
웹 서비스에 필요한 부분(이미지 업로드, 결과 이미지 URL, request_id 서버 생성)을 추가한다.
`backend/` 의 독립 FastAPI 앱은 `src/ad_service/api/` 로 흡수한다.

---

## 1. 공통 규약

| 항목 | 값 |
|---|---|
| Base URL (개발) | `http://localhost:8000` / 컨테이너 내부 `http://api:8000` |
| API prefix | `/api/v1` |
| 콘텐츠 타입 | 요청/응답 `application/json` (이미지 포함 시 `multipart/form-data`) |
| 문자셋 | UTF-8 |
| 인증 | MVP 없음 (→ 결정 필요) |
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
| 404 | `NOT_FOUND` | 존재하지 않는 asset/request_id |
| 413 | `PAYLOAD_TOO_LARGE` | 이미지 용량 초과 (기본 10MB) |
| 422 | `VALIDATION_ERROR` | 스키마 검증 실패 (필드 조합 오류 포함) |
| 429 | `BUDGET_EXCEEDED` | 요청 비용이 예산 캡 초과 |
| 500 | `INTERNAL_ERROR` | 처리되지 않은 서버 오류 |
| 503 | `MODEL_UNAVAILABLE` | 추론 백엔드(모델/Triton) 응답 불가 |

---

## 2. 엔드포인트 목록

| 메서드 | 경로 | 용도 |
|---|---|---|
| `GET` | `/health` | 헬스체크 (배포·모니터링용, prefix 없음) |
| `POST` | `/api/v1/generate` | 광고 문구·이미지 생성 (메인) |
| `GET` | `/api/v1/assets/{asset_id}` | 생성된 이미지 파일 반환 |
| `POST` | `/api/v1/uploads` | (옵션 B 채택 시) 입력 이미지 선업로드 |

---

## 3. `GET /health`

배포 스크립트와 compose healthcheck가 사용. 인증 없음, prefix 없음.

**200 OK**
```json
{ "status": "ok", "service": "ad_service", "version": "0.1.0" }
```

---

## 4. `POST /api/v1/generate`

### 4.1 요청

이미지 없이: `Content-Type: application/json` 으로 아래 본문.
이미지 포함: `Content-Type: multipart/form-data`, 파트 `payload`(아래 JSON 문자열) + 파트 `image`(파일).

```jsonc
{
  // 없으면 서버가 생성해서 응답에 담아 돌려준다. 클라이언트 재시도 시 같은 값 재사용 권장.
  "request_id": "a1b2c3d4",

  // 제품/상황 설명. outputs 에 "copy" 가 있으면 필수.
  "text": "국산 딸기로 만든 300g 수제 딸기잼. 유리병 포장.",

  // 생성할 결과 종류. 1~4개, 중복 불가.
  "outputs": ["copy", "banner"],

  "options": {
    "business_type": "food_retail",                 // 현재 MVP 고정
    "product_category": "packaged_food",             // packaged_food | snack_beverage | side_dish_meal
    "sales_channel": "smart_store",                  // smart_store | social_media | delivery_app | offline_store
    "campaign_goal": "purchase_conversion",          // product_launch | promotion | brand_awareness | purchase_conversion
    "target_audience": "간편한 아침 식사를 준비하는 20~40대",
    "tone": "밝고 믿음직한",
    "copy_style": "informative",                     // emotional | informative | conversion | friendly | premium | custom
    "copy_length": "standard",                       // short | standard | detailed
    "use_emoji": false,
    "must_include": ["국산 딸기", "300g"],           // 최대 5개, 각 60자 이하
    "avoid_phrases": ["최고", "건강에 좋은"],         // 최대 10개
    "custom_instruction": null,                      // copy_style == "custom" 이면 필수
    "price": null,
    "offer": null,
    "store_name": null                              // ← 신규 (프론트 요구). 결정 필요
  },

  // 자유 메타데이터. 서버는 저장만 하고 해석하지 않음 (실험 ID 등).
  "source": { "channel": "web" }
}
```

#### 필드 규칙

| 필드 | 타입 | 필수 | 비고 |
|---|---|---|---|
| `request_id` | string `^[a-zA-Z0-9_-]{1,80}$` | X | 생략 시 서버 생성 |
| `text` | string ≤ 2000자 | 조건부 | `outputs` 에 `copy` 포함 시 필수. 공백만 있으면 없는 것으로 처리 |
| `image` (multipart) | 파일 | X | jpg/png/webp, ≤ 10MB |
| `outputs` | `["copy"|"banner"|"detail_visual"|"product_image"]` | O | 1~4개, 중복 불가 |
| `options.*` | 위 예시 참조 | X | 전부 기본값 있음 |

#### 검증 규칙 (422 발생 조건)

- `text` 와 `image` 가 둘 다 없음 → 무엇을 만들지 알 수 없음
- `outputs` 에 `copy` 가 있는데 `text` 없음
- `options.copy_style == "custom"` 인데 `custom_instruction` 없음
- `must_include` 와 `avoid_phrases` 에 같은 표현
- `outputs` 중복

#### 입력 모드 (`mode`)

서버가 입력 조합으로 판정해서 응답에 명시:

| text | image | mode |
|---|---|---|
| O | X | `text_only` |
| X | O | `image_only` |
| O | O | `text_and_image` |

### 4.2 응답

**200 OK**

```jsonc
{
  "request_id": "a1b2c3d4",
  "mode": "text_only",

  // outputs 에 "copy" 가 있을 때만 존재
  "copy": {
    "product_summary": "국산 딸기를 담은 수제 딸기잼 300g",
    "headline_candidates": ["아침이 달라지는 국산 딸기잼", "...", "..."],   // 3개, 각 ≤ 25자
    "body_candidates": ["...", "...", "..."],                              // 3개, 각 ≤ 90자
    "cta_candidates": ["구매하기", "담기", "더보기"],                       // 3개, 각 ≤ 8자
    "keywords": ["국산 딸기", "수제잼", "300g"],
    "warnings": []
  },

  // outputs 의 이미지 종류마다 1개
  "assets": [
    {
      "type": "banner",                       // banner | detail_visual | product_image
      "url": "/api/v1/assets/a1b2c3d4_banner.png",
      "width": 1536,
      "height": 1024,
      "model": "gpt-image-2",
      "seed": 12345,                          // 없을 수 있음 (null)
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
```

- `copy` 는 `outputs` 에 `copy` 없으면 생략(또는 `null`).
- `assets` 는 이미지 outputs 없으면 `[]`.
- 일부 output 이 실패해도 나머지는 반환하고, 실패분은 `errors` 에 문자열로 기록 (부분 성공 허용).

### 4.3 프론트엔드 필드 매핑 (thlee `frontend/app.py` 수정 필요)

| 현재 프론트 필드 | 새 스펙 위치 | 변환 |
|---|---|---|
| `store_name` "OO 카페" | `options.store_name` | 그대로 (신규 필드, 결정 필요) |
| `business_type` "카페/디저트" | `options.business_type` + `options.product_category` | 한글 라벨 → enum 매핑 테이블 필요 |
| `target_audience` | `options.target_audience` | 그대로 |
| `keywords` "수제 디저트, 분위기 좋은" | `options.must_include` | 쉼표로 split → 배열 |
| `tone_manner` "친근하고 재치 있는" | `options.tone` + `options.copy_style` | 라벨 → enum 매핑 |
| (없음) | `outputs` | 프론트에서 체크박스로 선택하게 추가 (기본 `["copy","banner"]`) |
| (없음) | `text` | 프론트에 제품 설명 입력란 추가 (copy 생성에 필수) |

응답 읽기:
- 현재 `result.get("ad_text")` → `result["copy"]["headline_candidates"][0]` (+ body/cta)
- 현재 `result.get("image_url")` → `result["assets"][0]["url"]` (앞에 API host 붙여서 로드)

---

## 5. `GET /api/v1/assets/{asset_id}`

`POST /generate` 응답의 `assets[].url` 이 가리키는 이미지 파일을 반환.

- 200: `image/png` 바이너리
- 404: 존재하지 않는 asset
- `asset_id` 는 `^[a-zA-Z0-9_-]+\.(png|jpg|webp)$` 만 허용 (경로 탈출 방지)

저장 위치: `data/outputs/api/{request_id}/...` (설정 `AD_OUTPUT_ROOT`).

---

## 6. (옵션 B) `POST /api/v1/uploads`

이미지 입력을 `generate` 와 한 요청(multipart)으로 보내지 않고 분리하는 방식.

**요청**: `multipart/form-data`, 파트 `image` (파일)
**200 OK**: `{ "image_id": "up_xxx", "expires_at": "2026-09-10T12:00:00Z" }`

이후 `generate` 요청 본문에 `"image_id": "up_xxx"` 로 참조.
→ 재시도/큰 파일에 유리하지만 구현이 늘어남. **MVP 는 옵션 A(단일 multipart) 권장.**

---

## 7. 확정이 필요한 결정 (팀 회의 안건)

| # | 안건 | 기본안 | 결정 |
|---|---|---|---|
| D1 | API prefix `/api/v1` 통일 (cjpark 현재 `/v1`, 프론트 `/api/v1`) | `/api/v1` 채택 | |
| D2 | 생성 요청 동기 vs 비동기 | MVP 동기 (200 즉시). 이미지 latency 커지면 202+폴링 전환 | |
| D3 | 이미지 입력 방식 | 옵션 A: `generate` 에 multipart 단일 요청 | |
| D4 | `store_name` 등 매장 정보 필드 추가 위치 | `options.store_name` 신규 | |
| D5 | MVP 가 실제 지원할 `outputs` | `copy`, `banner` 우선 / `detail_visual`·`product_image` 후순위 | |
| D6 | 인증 | MVP 없음 → 배포 시 재검토 | |
| D7 | `request_id` 생성 주체 | 클라이언트 선택 제공, 없으면 서버 생성 | |
| D8 | asset 저장소 | 로컬 디스크 + API 서빙 / 나중에 GCS | |
| D9 | 프론트 한글 라벨 → enum 매핑표 소유자 | 프론트(thlee)가 표 제안 → API 담당 확정 | |
| D10 | `text` 최대 길이 (스키마 2000 vs `app_config.yaml` 4000) | 2000 으로 통일 | |
| D11 | `backend/` 디렉터리 폐기하고 `src/ad_service/api/` 로 단일화 | 단일화 | |

---

## 8. 예시 요청 모음

`examples/requests/` 에 실제 JSON 파일로 관리 (cjpark 브랜치에 이미 시작됨).
프론트·백·모델이 모두 이 파일들로 테스트한다.

| 파일 | 시나리오 |
|---|---|
| `copy_only.json` | 텍스트만 → 문구만 |
| `copy_and_banner.json` | 텍스트만 → 문구 + 배너 이미지 |
| `image_text.json` | 텍스트 + 상품 사진 → 배너 |
| `validation_error.json` | 일부러 422 나는 요청 (테스트용) |

---

## 9. 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v0.1 | 2026-09-10 | 초안. 3갈래 계약 통합안 제시, 결정 안건 D1~D11 도출 |
