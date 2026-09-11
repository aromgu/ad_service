# 팀 연결용: 상세페이지 mock-0.1

## 팀에 전달할 요약

모델 파트에서 **상품 정보 → 상세페이지 섹션/블록 JSON** mock을 준비했습니다.
현재는 AI 생성이 아니라 입력 사실과 고정 문구를 구조화하는 연결 테스트입니다.
실제 이미지 생성·파일 저장·네이버 연동·부분 수정은 포함하지 않습니다.

`POST /v1/mock/detail-pages`로 `request.json`을 보내면 `response.json` 형태의 결과를 받습니다.
이 묶음에는 서버 프로그램이 포함되어 있지 않습니다. 최신 구현 코드가 있는 저장소에서 서버를 실행하거나,
서버 연결 전 `response.json`을 화면용 fixture로 사용할 수 있습니다.

## 파일 구성

| 파일 | 용도 |
|---|---|
| request.json / response.json | 가상 머그 입력과 API에서 얻은 200 응답 |
| sparse.request.json / sparse.response.json | 사진·사실이 없는 입력과 섹션 생략 예시 |
| invalid.request.json / invalid.response.json | 잘못된 주 이미지 ID 입력과 실제 422 응답 |
| request.schema.json / response.schema.json | 구현된 Pydantic 모델에서 내보낸 JSON Schema |
| manifest.json | 버전, 예시 HTTP 상태, 파일별 SHA-256. 작성자가 임의 변경했는지 비교용 |
| README.md | 이 연결 안내 |

JSON은 실제 mock API 호출 결과이며 생성 모델의 추론 결과가 아닙니다. 자산 ID는 설명용이고
이미지 바이너리·URL·API 키·상품 원본·사용자 개인정보는 포함하지 않았습니다.
manifest는 암호학적 서명이 아니므로 배포자의 신원을 보장하지 않습니다.

## 호출 방법

서버 담당자가 현재 구현을 받은 저장소에서:

```bash
PYTHONPATH=src .venv/bin/python -m uvicorn ad_service.api.main:app --host 127.0.0.1 --port 8001
```

공유 묶음을 풀어 놓은 폴더의 다른 터미널에서:

```bash
curl --fail-with-body http://127.0.0.1:8001/v1/mock/detail-pages \
  -H 'Content-Type: application/json' --data-binary @request.json
```

`localhost`는 각자 컴퓨터를 뜻합니다. 다른 팀원이 이 주소를 그대로 사용하면 내 서버에 연결되지 않습니다.
다른 개발 포트의 브라우저에서 직접 요청하면 CORS가 필요할 수 있습니다. 현재 앱은 범용 CORS를
열지 않았으므로 서비스 개발 프록시/백엔드를 통해 연결하는 방식을 우선 협의하세요.
인증·작업 접근제어가 없는 개발 앱이므로 공용 IP에 노출하지 마세요.

## 프론트·서비스가 사용할 필드

- `sections[]`: 배열 순서대로 표시, `visible: false`인 섹션은 숨기는 구조입니다. 현재 생성값은 true입니다.
- `section_id`, `blocks[].block_id`: 선택·편집 키. 문서 간에는 같은 값이 나올 수 있으므로 문서 ID와 함께 관리하세요.
- `text` 블록: `role`에 맞게 제목/본문/특징/CTA를 표시합니다. 문자열은 HTML로 실행하지 마세요.
- `table` 블록: `rows[].label/value`를 상품 정보표로 표시합니다.
- `image` 블록: `source_asset_id`를 업로드 자산 맵에 연결합니다. `reference_only`는 새 생성 이미지가 아닙니다.
  샘플 ID가 실제 자산 맵에 없으면 자리표시자로 보여주세요.
- `fact_refs`: 원본 사실 추적용이며 사실의 진실성을 보증하지 않습니다.
- `review.missing_fields`, `omitted_sections`, `warnings`: 추가 확인 안내용입니다.
- `status: needs_review`: HTTP 호출은 성공했지만 사용자가 콘텐츠를 검수해야 한다는 뜻입니다.
- `persisted: false`: 저장은 하지 않았습니다. 서비스에서 문서 ID/버전/소유권을 관리해야 합니다.
- `execution.mode: mock`, `model_calls: 0`: 실제 AI 생성 완료로 표시하지 마세요.

타깃·톤·지시문은 현재 문구에 적용하지 않으며 응답 경고에 표시합니다. 한국어와
hero/features/specifications/cta만 지원합니다. 확정된 UI 정책이 아닌 mock의 임시 범위입니다.

## 연결 확인 체크리스트

1. 기본 요청이 HTTP 200으로 돌아오고 4개 섹션·8개 블록이 표시되는가?
2. 상품명과 정보표의 도자기·350mL·아이보리가 입력과 같은가?
3. sparse 요청에서 hero/cta만 남고 특징·정보표 생략 이유를 확인할 수 있는가?
4. invalid 요청에서 HTTP 422와 `detail` 오류를 표시하며 기존 화면을 덮어쓰지 않는가?
5. mock·미저장·검수 필요·이미지 참조 상태를 실제 생성/저장 완료와 구분하는가?

이 목록은 연결 담당자가 확인할 항목이며, 프론트 연결이 이미 완료됐다는 뜻은 아닙니다.
UI가 바뀌면 필요한 필드·블록 종류를 모델 파트와 조정하고 스키마 버전을 함께 갱신합니다.
