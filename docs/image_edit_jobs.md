# 상세페이지 승인형 이미지 편집 작업 — image-edit-job-0.1

에디터 왼쪽 챗봇이 만든 `edit_image` 의도를 바로 유료 모델에 보내지 않고
**작업 등록 → 사양·비용 확인 → 사용자 승인 → 1회 실행 → 결과 검수**로 분리한다.
현재 구현은 기존 상세페이지 불변 버전과 원본 이미지 자산을 보존하며, 검수한 편집 결과만
새 자산 ID와 새 문서 버전으로 붙인다.

## 실행 흐름

1. `revision-plan` 또는 `revision-preview`가 `ImageEditIntent(status=not_started)`를 반환한다.
2. 서비스가 저장된 최신 문서와 intent를 사용해 이미지 편집 작업을 등록한다.
3. 서버는 대상 블록·자산, 문서 버전/SHA256, 원본 파일 SHA256, 프롬프트, 모델·품질,
   출력 규격, 예상 비용을 고정한 `approval_sha256`을 반환한다. 이때 모델 호출은 0회다.
4. 프론트는 위 내용과 경고를 사용자에게 표시한다.
5. 사용자가 같은 `approval_sha256`과 허용 비용 상한을 승인하면 서버가 모든 값을 다시 검사한다.
6. 검사에 성공한 경우에만 이미지 제공자를 한 번 호출하고 PNG 결과를 저장한다.
7. 서버가 편집 결과를 새 자산으로 연결한 상세페이지와 HTML을 저장 없이 미리 보여 준다.
8. 사용자가 결과 이미지 SHA256·문서 SHA256·HTML SHA256을 승인하면 이미지 블록 참조를
   새 자산으로 바꾼 불변 문서 버전을 저장한다. 이전 문서와 원본 자산은 그대로 남는다.

승인 API는 현재 동기식 MVP다. 외부 모델 호출이 길어지는 운영 환경에서는 같은 저장 계약을
작업 큐가 실행하고 프론트가 조회 API를 폴링하거나 이벤트를 받도록 서비스 파트에서 바꿀 수 있다.

## API

### 작업 등록

`POST /v1/detail-pages/documents/{document_id}/image-edit-jobs`

```json
{
  "job_id": "edit_cosmetics_hero_001",
  "base_revision": 2,
  "base_document_sha256": "문서 SHA256 64자리",
  "intent": {
    "block_id": "hero_photo",
    "source_asset_id": "cosmetics_front",
    "instruction": "상품은 유지하고 배경만 따뜻한 아이보리색으로 바꿔줘",
    "status": "not_started"
  },
  "seed": 0
}
```

응답의 핵심 필드는 `status=pending_approval`, `prompt`, `provider`, `quality`,
`output_size`, `estimated_cost_usd`, `approval_sha256`이다. `model_calls=0`과
`image_generation_calls=0`이어야 한다.

### 승인과 실행

`POST /v1/detail-pages/image-edit-jobs/{job_id}/approve`

```json
{
  "operation_id": "approve_edit_cosmetics_hero_001",
  "approval_sha256": "등록 응답의 approval_sha256",
  "approved_cost_cap_usd": 0.01
}
```

사양 해시가 다르거나 승인 비용이 예상 비용보다 낮으면 409로 거부한다. 문서 버전·이미지 참조나
원본 파일이 등록 이후 바뀌어도 실행하지 않는다. 성공하면 `status=succeeded`,
`result_asset_id`, `result_asset_url`, `recorded_cost_usd`, 실제 지연시간을 반환한다.
같은 승인 요청 재전송은 기존 결과를 반환하며 모델을 다시 호출하지 않는다.

### 상태와 결과

- `GET /v1/detail-pages/image-edit-jobs/{job_id}`: 작업 상태와 승인·실행 메타데이터
- `GET /v1/detail-pages/image-edit-jobs/{job_id}/result`: 완료된 PNG 결과

### 문서 반영 미리보기와 승인

`POST /v1/detail-pages/image-edit-jobs/{job_id}/attachment-preview`

완료 이미지를 새 자산 ID로 추가하고 대상 이미지 블록만 교체한 상세페이지 문서와 HTML을
저장 없이 반환한다. 응답은 `result_file_sha256`, `document_sha256`, `html_sha256`을 포함하며
모델 호출은 0회다. 이 호출만으로 현재 문서 버전은 바뀌지 않는다.

`POST /v1/detail-pages/image-edit-jobs/{job_id}/attach`

```json
{
  "operation_id": "attach_edit_cosmetics_hero_001",
  "approved_document_sha256": "미리보기의 문서 SHA256",
  "approved_html_sha256": "미리보기의 HTML SHA256",
  "approved_result_file_sha256": "미리보기의 결과 이미지 SHA256"
}
```

서버는 저장된 최신 문서에서 미리보기를 다시 만들고 세 해시가 모두 일치할 때만 다음 버전을
저장한다. 동일 승인 재전송은 기존 버전을 반환한다. 일반 텍스트 승인과 동시에 충돌하면 문서 잠금과
기준 버전 검사를 통해 하나만 성공하며, 실패한 요청이 현재 문서를 덮어쓰지 않는다.

## 현재 지원 범위와 안전장치

- 공급자: 비용 없는 `mock`, 실제 참조 이미지 편집을 지원하는 `gpt-image-2`.
  FLUX 배경 생성 모델은 이 직접 편집 작업에서 선택할 수 없다.
- 원본: 모델 서비스가 관리하는 `/v1/results/{request_id}/{filename}` 자산만 실행 대상으로 쓴다.
  API가 클라이언트의 임의 로컬 파일 경로나 외부 URL을 받아 열지 않는다.
- 출력 규격: 원본 종횡비에 따라 `1024x1024`, `1024x1536`, `1536x1024` 중 하나를 고정한다.
- 비용: 프로젝트의 고정 견적표를 승인 화면에 표시하고 서비스 누적 예산도 실행 직전에 확인한다.
  실제 청구 금액은 공급자 사용량 자료로 별도 대조해야 한다.
- 보존: 프롬프트는 상품 형태·로고·인쇄 문구 보존과 새 문자 생성 금지를 명시하지만,
  생성형 편집이 이를 완전히 보장하지 않으므로 결과는 사람이 원본과 비교해야 한다.
- 반영: 결과 파일을 원본 자산에 덮어쓰지 않는다. 새 자산을 추가하고 대상 블록 참조만 바꾼
  새 문서 버전을 만들며, 이미지·문서·HTML 해시를 다시 대조한다.
- 중복: 작업 파일 잠금과 승인 요청 해시로 동시·재전송 호출을 한 번으로 제한한다.
- 장애: 외부 호출 시작 뒤 연결이 끊기면 무조건 자동 재호출하지 않는다. 실패 작업은 새 작업으로
  다시 사양과 비용을 승인한다.

현재 로컬 저장소에는 사용자 인증과 상품 소유권 검사가 없다. 외부 공개 전에 서비스 계층이
문서·원본 자산·작업에 같은 사용자 소유권을 강제해야 한다.

## 검증

```bash
PYTHONPATH=src .venv/bin/pytest -q tests/integration/test_image_edit_job.py
```

테스트는 등록 전 호출 금지, 승인 후 mock 1회 실행, 잘못된 승인/원본 변경/문서 충돌 차단,
비용 상한, 관리되지 않은 경로 거부, 동시 중복 승인, 편집 결과의 미리보기·불변 버전 반영과
결과 파일 변조 차단을 확인한다. 실제 유료 API는 호출하지 않는다.
