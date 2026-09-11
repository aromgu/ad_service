# 상세페이지 공통 수정 구조 — revision-0.1

모델 파트의 **자연어 수정 계획·구조화된 수정안 검증·HTML 미리보기** 단계다.
제목만 고치는 기능이 아니다. 왼쪽 채팅 UI에서 받은 지시를 수정안으로 바꾸는 모델까지
연결했으며, 검증된 문서를 실행 코드 없는 HTML로 렌더링하는 API까지 제공한다.
사용자가 승인한 HTML 해시를 다시 대조해 새 불변 버전으로 저장하는 API도 제공한다.
생성형 이미지 편집은 [승인형 이미지 편집 작업](image_edit_jobs.md)으로 분리해 연결했다.
편집 결과도 별도 검수 후 새 문서 자산과 불변 버전으로 확정한다.

## 흐름과 역할

사용자 지시 + 최신 문서 + 선택 범위 → 모델이 수정 대상/작업 제안
→ 수정안 검증·JSON 미리보기 → 안전한 HTML 미리보기 → [프론트: 사용자 승인]
→ 서버가 저장된 최신 버전 재검증 → 새 불변 버전 저장

대상이 모호하거나 새 상품 정보가 필요한 경우 모델은 `needs_clarification`과
질문을 반환해야 한다. 검증기는 질문과 수정 작업을 함께 반환하는 것을 거부한다.
자연어 계획기는 검증된 `facts` 밖의 상품 사실을 만들지 않도록 지시되지만, 외부 사실을
검증하는 도구는 아니다. 구조 검증기가 대상·참조·수정 범위·버전 충돌을 추가로 차단한다.

## 지원 작업

| 작업 | 용도 |
|---|---|
| replace_text | 제목·본문·특징·CTA 문구 변경 |
| replace_image | 문서에 등록된 다른 이미지 참조로 교체 |
| edit_image | 배경 변경 등 생성형 편집의 **미실행 작업 의도** 기록 |
| set_style | 색상·배경색·글자 크기·정렬·너비 중 지정한 속성만 변경 |
| set_layout | 섹션 레이아웃 프리셋 변경 |
| add/remove/move_block | 섹션 내부 요소 추가·삭제·이동 |
| add/remove/move_section | 섹션 추가·삭제·순서 이동 |
| replace_table | 판매자가 제공한 사실을 이용한 정보 표 변경 |

전체 페이지 변경은 필요한 작업 여러 개로 표현한다. 사진 교체는 파일 수정이
아니라 자산 ID 참조 변경이다. 사진 편집은 `not_started`로 반환하며 API를 호출하거나
백그라운드 작업을 등록하지 않는다. 자연어로 임의 CSS/코드 실행은 지원하지 않는다.
새 레이아웃이나 도표 같은 미지원 요청은 구조를 확장하거나 사용자 확인으로 넘긴다.

## 보존과 검증

- 섹션/블록에 고정 ID를 사용한다. 지정하지 않은 내용·스타일·사진 참조는 보존한다.
- 원본 깊은 사본에 작업을 순서대로 적용한다. 하나라도 실패하면 전체 결과를 거부한다.
- `base_revision` + 정규화 문서 `SHA256` 비교로 전달받은 문서와 수정안의 불일치를 차단한다.
- 미리보기 API는 무상태지만 승인 API는 서버가 **저장된 최신 문서**를 다시 불러온다.
  클라이언트 사본을 최신 문서로 신뢰하지 않으며 파일 잠금 안에서 버전·해시를 비교한다.
- 직접 변경이 있으면 초안 revision을 한 번 증가한다. 질문/이미지 작업 의도만 있으면 유지한다.
- 승인 전 삭제도 미리보기일 뿐이다. 승인 후에는 새 버전으로 저장하고 이전 버전을 보존한다.
- 이미지/사실 ID 존재와 표 값의 원문 일치를 검사한다. 자산 접근 권한·실제 파일 존재는 별도 검증한다.
- 일반 문구는 사실 참조가 있어도 진실임을 보장하지 않는다. 소재·효능·인증 등을
  만들어 쓰지 않도록 모델 지시·판매자 확인을 추가해야 한다.
- 빈 페이지/빈 섹션, 중복 ID, 범위 밖 이동, 없는 대상, 임의 스타일·작업은 거부한다.
  이동 index는 원래 항목을 제거한 후의 0부터 시작하는 위치다.
- 문자열은 JSON 데이터다. 프론트/HTML 렌더러는 반드시 이스케이프한다.

## API와 재현

`POST /v1/detail-pages/revision-plan`

왼쪽 챗봇용 엔드포인트다. 최신 `document`, 사용자 `instruction`, 선택한 섹션·블록 ID를
받아 모델이 `proposal`을 한 번 만들고, 서버가 같은 요청 안에서 검증한 `preview`를 반환한다.
대상이 모호하면 `needs_clarification`과 질문만 반환한다. 자동 저장과 이미지 생성은 하지 않는다.

`POST /v1/detail-pages/revision-preview`

입력: `document` + `proposal` (`request_id`, `base_revision`, `base_sha256`,
`instruction`, `decision`, `question`, `operations`).
응답: 수정된 문서 사본·새 hash·변경 작업·미실행 이미지 작업 의도.
`persisted=false`, `model_calls=0`. 충돌 409, 잘못된 구조/작업 422.

`POST /v1/detail-pages/revision-render-preview`

입력: 위 `document` + `proposal`과 자산 ID별 안전한 동일 출처 상대·루트 경로 `asset_urls`.
서버가 버전·해시·모든 수정 작업을 다시 검증한 뒤 수정 문서와 완성 HTML, HTML SHA256을
한 번에 반환한다. 임의 CSS·JavaScript를 받거나 실행하지 않고 모든 문구와 대체 텍스트를
이스케이프한다. 문서 자산과 URL 매핑이 하나라도 빠지거나 남으면 422로 거부한다.
확인 질문이 필요한 수정안에는 HTML을 만들지 않는다. 모델 호출·파일 저장·이미지 생성은
모두 0회이며 `persisted=false`다. 프론트는 결과를 스크립트 권한 없는 격리 iframe에 표시한다.

`POST /v1/detail-pages/documents`

검수가 끝난 최초 `document`, `asset_urls`, 고유 `operation_id`를 첫 불변 버전으로 등록한다.
문서 JSON·HTML·자산 경로·메타데이터를 함께 저장하며 원본 자산 자체는 복사하지 않는다.

`POST /v1/detail-pages/documents/{document_id}/approve`

입력은 미리보기에서 받은 `proposal`, `approved_document_sha256`, `approved_html_sha256`과
고유 `operation_id`다. 서버는 저장된 최신 문서를 읽어 수정안을 다시 적용·렌더링하고 두 해시가
모두 일치할 때만 새 버전을 저장한다. 같은 `operation_id`와 같은 요청은 기존 결과를 반환하고,
같은 ID에 다른 요청을 쓰거나 오래된 기준 버전으로 승인하면 409를 반환한다. 동시 승인도 파일
잠금 안에서 하나만 성공한다. 실행되지 않은 이미지 편집 의도가 남아 있으면 승인할 수 없다.

조회 API는 다음과 같다.

- `GET /v1/detail-pages/documents/{document_id}`: 최신 문서와 해시
- `GET /v1/detail-pages/documents/{document_id}/revisions`: 전체 불변 버전 이력
- `GET /v1/detail-pages/documents/{document_id}/revisions/{revision}/document`: 특정 문서
- `GET /v1/detail-pages/documents/{document_id}/revisions/{revision}/html`: 특정 HTML

HTML 응답은 스크립트·외부 자산을 막는 CSP와 `nosniff` 헤더를 포함한다. 현재 저장소는
로컬 파일 기반이며 사용자 인증·상품 소유권 검사는 서비스 계층에서 추가해야 한다.

`POST /v1/detail-pages/documents/{document_id}/image-edit-jobs`

미실행 `ImageEditIntent`를 저장된 최신 문서와 대조한 뒤 모델·품질·프롬프트·원본 SHA256·예상
비용을 고정한 승인 대기 작업으로 등록한다. 이 단계의 모델·이미지 호출은 0회다. 임의 로컬 경로나
외부 URL은 열지 않고 모델 서비스가 관리하는 `/v1/results/...` 원본만 허용한다.

`POST /v1/detail-pages/image-edit-jobs/{job_id}/approve`

사용자가 등록 응답의 `approval_sha256`과 비용 상한을 승인하면 문서 버전·원본 해시·사양을 다시
검사하고 기존 이미지 제공자를 한 번 호출한다. 동일 승인 재요청은 기존 결과를 반환한다. 상태는
`GET /v1/detail-pages/image-edit-jobs/{job_id}`, 완료 PNG는 해당 작업의 `/result`에서 조회한다.
`POST /v1/detail-pages/image-edit-jobs/{job_id}/attachment-preview`는 성공 결과를 새 자산으로
연결한 문서·HTML을 저장 없이 반환한다. 이어 `/attach`에서 결과 이미지·문서·HTML 해시를 모두
재검증한 뒤 대상 이미지 블록만 새 자산으로 바꾼 불변 버전을 저장한다. 원본 이미지와 이전 문서는
덮어쓰지 않는다.

```bash
PYTHONPATH=src .venv/bin/python scripts/export_revision_examples.py \
  --source ../outputs/photo_detail_20260910_001/outfit \
  --output ../outputs/revision_examples_20260910_001/outfit
```

의류·화장품의 이전 **실제 모델 분석 결과**를 문서로 변환하되 사진 분석을 확인된
상품 사실로 승격하지 않는다. `facts`는 비우고 미확인 항목과 주의사항을 보존한다.
관찰 근거와 OCR 후보는 원본 result.json에 남겨 두며 새 문서의 검증 사실로 쓰지 않는다.
예제 수정 문구와 작업은 수작업 테스트 값이다. AI 수정 품질 평가로 기록하지 않는다.
기존 HTML·사진·모델 응답은 덮어쓰지 않는다. 출력 폴더가 존재하면 실행을 거부한다.

## 다음 연결 순서

1. 실제 자연어 → 대상 ID·작업 목록·확인 질문을 반환하는 모델 연결 및 범위 평가.
2. 수정 의도/요청 범위를 벗어난 작업을 차단하는 검증, 사실 추가 요청 시 확인 절차.
3. 완료: 텍스트·레이아웃 수정 문서를 안전한 HTML 미리보기 렌더러에 연결.
4. 완료: 승인 해시 대조, 불변 버전 저장·조회, 동시 충돌·작업 중복 방지 구현.
5. 완료: 이미지 편집 의도를 기존 이미지 제공자의 승인형 작업에 연결.
6. 완료: 검수한 이미지 결과를 새 자산으로 추가하고 새 문서 버전으로 승인.
7. 다음: 사용자 인증·상품 소유권과 운영 저장소를 서비스 계층에 연결.

이 스키마는 고정 UI가 아닌 모델-백엔드 협의 초안이며 기존 mock-0.1 계약을 대체하지 않는다.
