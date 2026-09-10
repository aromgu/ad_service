# API 명세서 (v1.0) — 백엔드 ↔ AI 모델

## 0. 이 문서의 범위

**백엔드(`web/backend`)가 모델 서버(`src/ad_service`)를 호출하는 계약**만 다룬다.


- 엔드포인트 목록: <http://localhost:8000/docs> (FastAPI 자동 생성)
- 요청·응답 타입: `web/backend/app/schemas/common.py`
- 프론트 호출부: `web/frontend/src/lib/api.ts`

### v0.3 에서 무엇이 바뀌었나

v0.3 은 `copy` / `banner` 를 만드는 서비스를 전제로 쓰였다. 그 뒤 제품이
**스마트한 스미스 씨**(상세페이지 · 블로그 · 상품등록)로 확정되고 화면이 전부
구현되면서 입·출력이 달라졌다. 비동기 폴링 구조와 에러 형식은 v0.3 그대로 쓰고,
**작업 종류와 페이로드만 다시 정의한다.**

---

## 1. 모델 4개

| # | 모델 | `task` | 역할 |
| --- | --- | --- | --- |
| M1 | 상세페이지 생성 | `detail_page` | 상품 사진 + 폼 입력 → 상세페이지 문서 + 연출 이미지 |
| M2 | 상세페이지 수정 챗봇 | `document_edit` | 문서 + 사용자 요청 → 수정된 문서 |
| M3 | 블로그 작성 | `blog` | 사진 + 주제 → 블로그 초안 문서 |
| M4 | 상품등록 정보 추출 | `product_extract` | 상세페이지 이미지 → 네이버 등록용 필드 |

M2 는 M1·M3 결과물을 **공통으로** 고친다. 문서 구조가 같아서 모델을 나눌 이유가 없다.

---

## 2. 확정 사항 — 애매했던 두 가지

### D-A. 상세페이지는 **HTML 이 아니라 JSON 블록**으로 준다

모델은 `sections` 배열(JSON)을 돌려주고, **HTML 이 필요한 곳에서 백엔드가 렌더링**한다.

이유:

1. **에디터가 블록 단위로 동작한다.** 블록을 클릭해 글자 크기·굵기·정렬·색을 바꾸고
   삭제하고 이미지를 교체한다(프레임 2d). HTML 문자열을 받으면 이걸 하려고
   DOM 을 파싱해 되돌려야 한다.
2. **챗봇이 특정 블록만 고친다.** "히어로 문구 짧게" → `headline` 블록만 교체.
   HTML 이면 어디를 고쳐야 할지 다시 찾아야 한다.
3. **HTML 이 필요한 곳이 여러 개고 형식이 다 다르다.** 네이버 `detailContent`,
   HTML 내려받기, PNG 내보내기. JSON 하나에서 각각 렌더링하는 편이 안전하다.
4. **LLM 이 만든 HTML 은 예측이 안 된다.** 인라인 스타일·깨진 태그·스크립트가
   섞여 들어오고, 그대로 렌더링하면 XSS 위험이 있다. JSON 은 스키마로 검증된다.

> **모델은 HTML 을 만들지 않는다.** `detailContent` HTML 은 백엔드의 렌더러가
> `sections` 에서 생성한다 (`web/backend/app/naver/service.py`).

### D-B. 상품등록 모델은 **네이버 값을 직접 만들지 않는다**

상품등록은 네이버 검증이 까다롭다 — 카테고리 ID, 원산지 코드, 고시 항목, 태그 제한.
**모델이 이걸 지어내면 등록이 실패한다.** 그래서 역할을 이렇게 나눈다.

| | 모델이 하는 것 | 백엔드가 하는 것 |
| --- | --- | --- |
| 카테고리 | `category_query`: 검색어 배열 (예: `["세럼","에센스"]`) | 네이버 카테고리 API 로 `leafCategoryId` 확정 |
| 원산지 | 건드리지 않음 | 코드 `"00"`(국산) 고정 |
| 고시 항목 | 건드리지 않음 | 상품군 정의를 조회해 채움 |
| 이미지 | 건드리지 않음 | 네이버 이미지 API 로 업로드 후 URL 사용 |
| 상품명·브랜드·옵션·태그·속성 | **만든다** | 길이·형식만 검증 |

**모델이 절대 만들면 안 되는 값:** `leafCategoryId`, `originAreaCode`,
`productInfoProvidedNotice`, 네이버 이미지 URL, 택배사 코드.
숫자 ID 를 지어내면 400 으로 등록이 거절된다.

출력은 **고정 스키마 + enum** 으로 받는다. 자유 문자열은 검증 가능한 곳에만 둔다.
구현은 OpenAI `response_format: json_schema` 같은 **구조화 출력(structured output)**
기능을 쓴다 — 프롬프트로 "JSON 으로 주세요"라고 부탁하는 방식은 쓰지 않는다.

---

## 3. 공통 규약

### 3.1 전송

- Base URL: `http://{모델서버}/api/v1` (기본 `http://localhost:8100/api/v1`)
- `Content-Type: application/json`, UTF-8
- 이미지가 있으면 `multipart/form-data`
  - `payload` 파트 — 아래 JSON 을 문자열로
  - `images` 파트 — 파일 여러 개 (jpg/png/webp, 각 10MB 이하)

### 3.2 비동기 폴링 (v0.3 유지)

```
POST /api/v1/generate      → 202 {request_id, poll_url}
GET  /api/v1/jobs/{id}     → 진행률·결과
GET  /api/v1/assets/{id}/{filename}   → 생성된 이미지 파일
```

백엔드가 **0.6초 간격**으로 폴링한다. 화면(2b·3b·4b)의 진행률 원과 스텝
체크리스트가 이 응답을 그대로 그린다.

**접수 응답 (202)**

```json
{ "request_id": "a1b2c3d4", "status": "pending", "poll_url": "/api/v1/jobs/a1b2c3d4" }
```

**진행 중**

```json
{
  "request_id": "a1b2c3d4",
  "status": "running",
  "progress": 42,
  "step": "copy",
  "steps": [
    { "key": "analyze", "label": "상품 정보 분석", "state": "done" },
    { "key": "copy",    "label": "카피 문구 작성", "state": "active" },
    { "key": "layout",  "label": "레이아웃 구성",  "state": "pending" },
    { "key": "images",  "label": "이미지 배치",    "state": "pending" }
  ]
}
```

- `progress` — 0~100 정수
- `state` — `done` | `active` | `pending`
- 스텝 `key`·`label` 은 **모델 서버가 정한다.** 백엔드는 그대로 그린다.

**완료** — `status: "succeeded"` + `result` (작업별로 아래 4~7절)

**실패**

```json
{
  "request_id": "a1b2c3d4",
  "status": "failed",
  "error": { "code": "MODEL_TIMEOUT", "message": "이미지 생성이 응답하지 않았습니다." }
}
```

### 3.3 에러

| code | 뜻 | 백엔드 처리 |
| --- | --- | --- |
| `INVALID_INPUT` | 입력이 규격에 안 맞음 | 사용자에게 그대로 보여줌 |
| `MODEL_TIMEOUT` | 모델 응답 없음 | 작업 실패 → 내 작업의 실패 카드 |
| `MODEL_REFUSED` | 모델이 생성을 거절 | 사유를 사용자에게 보여줌 |
| `RATE_LIMITED` | 호출량 초과 | 지수 백오프 후 재시도 |
| `INTERNAL` | 그 외 | 작업 실패 |

`message` 는 **사용자에게 그대로 보여줄 한국어 문장**으로 쓴다. 스택트레이스나
영어 예외 문자열을 넣지 않는다.

### 3.4 시간 제한

| 작업 | 목표 | 상한 |
| --- | --- | --- |
| `detail_page` | 40초 | 3분 |
| `document_edit` | 10초 | 60초 |
| `blog` | 30초 | 2분 |
| `product_extract` | 60초 | 3분 |

상한을 넘기면 모델 서버가 `MODEL_TIMEOUT` 으로 끝낸다.

### 3.5 생성된 이미지

모델이 만든 이미지는 **파일로 저장하고 URL 로 준다.** base64 로 JSON 에 넣지 않는다
(문서가 수 MB 로 불어난다).

```
GET /api/v1/assets/{request_id}/{filename}
```

백엔드가 이 URL 을 내려받아 자기 저장소로 옮긴다. 모델 서버는 **24시간**만 보관하면 된다.

---

## 4. 공통 타입 — 문서 블록 (`Section`)

M1·M2·M3 의 결과물은 모두 이 배열이다. 현재 구현: `web/backend/app/schemas/common.py`

```jsonc
{
  "id": "a1b2c3d4e5f6",     // 12자 hex. 블록마다 고유. 수정 시 그대로 유지한다.
  "type": "headline",
  "visible": true,
  "content": { }             // type 마다 다름 (아래)
}
```

| `type` | `content` | 쓰이는 곳 |
| --- | --- | --- |
| `eyebrow` | `{ text, letterSpacing? }` | 상세페이지·블로그 머리말 |
| `headline` | `{ lines: string[], fontSize?, bold?, italic?, align?, color? }` | 제목. **줄바꿈은 배열 원소로** |
| `stat` | `{ prefix, value, suffix }` | "수분 보유력 **+38%** · 4주 임상" |
| `subclaim` | `{ text, fontSize?, ... }` | 보조 설명 |
| `heading` | `{ text, fontSize? }` | 블로그 소제목 |
| `paragraph` | `{ text }` | 블로그 본문 문단 |
| `image` | `{ url, alt, height?, caption? }` | 이미지 블록 |
| `note` | `{ text }` | "— 핵심 성분 섹션 이어짐 —" 같은 안내 |

규칙:

- `headline.lines` 는 **줄 단위 배열**이다. `"a\nb"` 로 주지 않는다.
- `image.url` 은 `GET /assets/...` 경로이거나, 입력으로 받은 원본 이미지 URL 이다.
- 모르는 `type` 이 오면 백엔드가 **그 블록만 건너뛴다** (문서 전체를 버리지 않는다).

---

## 5. M1 — 상세페이지 생성 (`detail_page`)

### 요청

```jsonc
{
  "task": "detail_page",
  "request_id": "a1b2c3d4",
  "input": {
    "product_name": "시카마누 바이옴 세럼",
    "target": "20-30대 여성",
    "language": "자동",              // 자동 | 한국어 | English | 日本語 | 中文
    "tone": "감성적",                 // 감성적 | 정보 중심
    "length": "숏(10장 내외)",        // 숏(10장 내외) | 미들(15장 내외) | 롱(20장 이상)
    "features": "피부 톤 개선, 보습 효과, 저자극 성분",
    "image_count": 2                 // multipart 로 함께 보낸 사진 장수 (1~5)
  }
}
```

### 응답 `result`

```jsonc
{
  "title": "시카마누 바이옴 세럼 상세페이지",   // 참고용. 카드 제목은 백엔드가 번호로 붙인다
  "sections": [ /* 4절 Section 배열 */ ],
  "thumbnail_url": "/api/v1/assets/a1b2c3d4/hero.png",
  "messages": [                                  // 에디터 좌측 채팅에 처음 뿌릴 대화
    { "role": "user",      "content": "…", "meta": {} },
    { "role": "assistant", "content": "…", "meta": {
        "summaryCard": [ { "label": "채널", "value": "스마트스토어" } ],
        "closing": "수정할 부분을 알려주세요.",
        "footer": "6개 블록 생성됨"
    }}
  ]
}
```

- `sections` 는 **1개 이상**. 첫 블록은 `eyebrow` 또는 `headline` 을 권장한다.
- 사진 연출컷(gpt image 2)을 만들면 `image` 블록의 `url` 에 넣는다.
- `messages` 가 비어 있어도 된다. 그러면 에디터 채팅이 빈 상태로 시작한다.

---

## 6. M2 — 상세페이지 수정 챗봇 (`document_edit`)

M1·M3 결과를 **공통으로** 고친다.

### 요청

```jsonc
{
  "task": "document_edit",
  "request_id": "a1b2c3d4",
  "input": {
    "document_type": "detail_page",       // detail_page | blog
    "sections": [ /* 현재 문서 전체 */ ],
    "message": "히어로 문구를 조금 더 짧게 줄여줘.",
    "history": [                           // 최근 대화 (최대 20턴). 없으면 빈 배열
      { "role": "user", "content": "…" },
      { "role": "assistant", "content": "…" }
    ],
    "attached_image_count": 0              // 사용자가 채팅에 올린 사진 장수
  }
}
```

### 응답 `result`

```jsonc
{
  "reply": "헤드라인을 2줄로 줄이고 임상 수치를 앞으로 당겼어요.",
  "sections": [ /* 수정된 문서 전체 */ ],
  "meta": { "footer": "1개 블록 수정됨" }
}
```

규칙:

- **문서 전체를 돌려준다.** 부분 패치(diff)는 쓰지 않는다 — 블록 순서·삭제까지
  표현하려면 전체가 단순하고 안전하다.
- **고치지 않은 블록은 `id` 를 그대로 유지한다.** 에디터가 선택 상태를 잃지 않는다.
- 요청을 수행할 수 없으면 `sections` 를 **입력 그대로** 돌려주고 `reply` 로 이유를 설명한다.
  빈 배열이나 `null` 을 주지 않는다.

---

## 7. M3 — 블로그 작성 (`blog`)

### 요청

```jsonc
{
  "task": "blog",
  "request_id": "a1b2c3d4",
  "input": {
    "topic": "캠핑용 접이식 미니 테이블",
    "style": "기본 블로그",          // 기본 블로그 | 체험단 리뷰 | 정보성 포스트 | 제품 비교
    "extra_request": "3040 주부 대상, 캠핑 초보 관점으로",
    "image_count": 3                 // 1~8
  }
}
```

### 응답 `result`

M1 과 같은 형식(`title` · `sections` · `thumbnail_url` · `messages`). 다만:

- `heading` + `paragraph` 블록을 주로 쓴다.
- 사진은 본문 흐름에 맞춰 `image` 블록으로 끼워 넣는다.
- 요약 카드(`meta.summaryCard`)의 **글자 수는 실제 본문에서 센 값**을 넣는다.
  에디터 상단 바가 같은 값을 따로 계산하므로 다르면 사용자가 혼란스럽다.

---

## 8. M4 — 상품등록 정보 추출 (`product_extract`)

**가장 규격이 빡빡한 모델이다.** D-B 를 반드시 지켜야 한다.

### 구현 방식

별도 모델을 학습하지 않는다. **VLM + 구조화 출력**으로 푼다:

1. 상세페이지 이미지들을 VLM 에 넣어 OCR + 시각 정보를 읽는다
2. 아래 JSON 스키마를 `response_format` 으로 강제한다
3. 스키마 위반 시 모델 서버가 **한 번 재시도**하고, 그래도 실패하면 `INVALID_INPUT`

### 요청

```jsonc
{
  "task": "product_extract",
  "request_id": "a1b2c3d4",
  "input": {
    "product_info": "구성품 본체 1개 · 소재 캔버스 · 사이즈 43×36cm",  // 선택. 있으면 이미지보다 우선
    "image_count": 9
  }
}
```

### 응답 `result` — 이 스키마를 벗어나면 거절한다

```jsonc
{
  "product_name": "PARK 페이즐리 에코백 캔버스 가방 43×36cm",  // 1~100자
  "brand": "PARK HERE",            // 0~100자. 모르면 빈 문자열
  "manufacturer": "PARK HERE",     // 0~100자
  "description": "…",              // 10~2000자. 상품 설명 본문

  // ★ 카테고리는 검색어만 준다. 네이버 ID 를 지어내지 않는다 (D-B).
  //   확신 순서대로 1~5개. 백엔드가 앞에서부터 조회해 맞는 것을 고른다.
  "category_query": ["에코백", "캔버스백", "여성가방"],

  "options": [                     // 0~50개. 없으면 빈 배열
    { "name": "화이트", "price": 0, "stock": 9838 }   // name 1~50자, price ≥ 0, stock ≥ 0
  ],

  "tags": ["에코백가방", "크로스백"],   // 0~10개, 각 1~20자.
                                       //  상품명·카테고리에 이미 있는 단어는 넣지 않는다
                                       //  (네이버가 "등록불가 단어"로 거절한다)

  "attributes": {                  // 속성명·값 모두 자유 문자열. 0~20쌍
    "사용대상": "여성",
    "패턴": "프린트",
    "주요소재": "캔버스"
  },

  "kc": { "mode": "none", "detail": "KC 대상 아님" },   // mode: "has" | "none"

  "price_suggestion": null,        // 정수 또는 null. 확신 없으면 null (사람이 정한다)

  "analysis": { "ocr_chars": 542 } // 참고 지표. 자유 형식
}
```

#### 반드시 지킬 것

| 규칙 | 이유 |
| --- | --- |
| `category_query` 는 **검색어**다. 숫자 ID 금지 | 네이버 카테고리 5002개를 모델이 외울 수 없다 |
| `tags` 에 상품명·카테고리 단어를 넣지 않는다 | 네이버가 "등록불가 단어"로 400 을 낸다 |
| `price_suggestion` 은 **확신 없으면 `null`** | 가격을 지어내면 실제로 그 값에 팔린다 |
| `options[].stock` 은 정수 | 문자열이면 등록이 거절된다 |
| `kc.mode` 는 `has` / `none` 둘 중 하나 | 그 외 값은 매핑할 곳이 없다 |
| 원산지·고시·이미지 URL 은 **넣지 않는다** | 백엔드가 채운다. 넣으면 무시된다 |

#### 백엔드가 이어서 하는 일

1. `category_query` → 네이버 카테고리 조회 → `leafCategoryId` 확정
2. 카테고리 경로 → 상품정보제공고시 상품군 결정 → 항목 정의 조회 → 채움
3. 이미지 → 네이버 이미지 API 업로드 → 반환된 URL 사용
4. 원산지 `"00"`(국산), 택배사 코드, 배송비 → 사용자의 배송 설정에서
5. `POST /v2/products` 호출 → `originProductNo` 저장

---

## 9. 검증과 실패 처리

- 모델 서버는 **자기 출력을 스스로 검증한다.** 스키마에 안 맞으면 한 번 재시도하고,
  그래도 안 되면 `INVALID_INPUT` 으로 실패시킨다. 깨진 결과를 백엔드로 넘기지 않는다.
- 백엔드도 **받은 뒤 다시 검증한다.** 모르는 블록 타입은 건너뛰고, 필수 필드가
  없으면 작업을 실패 처리한다.
- 부분 성공은 없다. 문서는 통째로 성공하거나 실패한다.

---

## 10. 아직 안 정한 것

1. **모델 서버 주소** — 지금은 `http://localhost:8100` 을 가정한다.
   컨테이너로 띄우면 서비스명으로 바꾼다. (Gu)
2. **인증** — 같은 VM 안이라 없다. 분리 배포하면 내부 토큰이 필요하다. (Gu)
3. **동시 처리 한도** — 모델 서버가 한 번에 몇 건을 받을 수 있는지.
   초과 시 `RATE_LIMITED` 로 돌려주면 백엔드가 대기시킨다. (Park)
4. **`product_extract` 의 이미지 장수 상한** — 상세페이지가 20장이 넘을 때
   전부 넣을지, 앞 N장만 볼지. (Park)

---

## 11. 지금 상태

백엔드는 위 계약을 **provider 인터페이스** 뒤에 두고 목업으로 돌고 있다.

```
web/backend/app/generation/
├── base.py       # GenerationProvider 프로토콜 — 위 계약과 1:1
├── mock.py       # 지금 쓰는 목업
└── registry.py   # GENERATION_PROVIDER 로 교체
```

모델 서버가 준비되면 `remote.py` 를 추가하고 `.env` 의
`GENERATION_PROVIDER=remote` 로 바꾼다. 프론트엔드·DB·화면은 바뀌지 않는다.

**네이버 커머스 연동은 이미 실제로 동작한다** (토큰·이미지 업로드·카테고리
조회·상품 등록·삭제 확인 완료). M4 의 출력만 들어오면 바로 실제 등록까지 이어진다.

---

## 변경 이력

| 버전 | 날짜 | 내용 |
| --- | --- | --- |
| v0.1~v0.3 | 2026-09 초 | copy/banner 기준 초안 (폐기) |
| **v1.0** | 2026-09-10 | 백엔드↔모델 계약으로 재작성. 모델 4개 정의, D-A·D-B 확정 |
