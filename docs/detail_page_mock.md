# 상세페이지 JSON mock 실행 안내

상태: **mock-0.1 구현 / 실제 생성 모델 미연결**

## 무엇을 확인할 수 있나

`POST /v1/mock/detail-pages`는 공통 상품 정보를 받아 섹션·블록 구조를 반환한다.
임의의 도소매 카테고리를 받을 수 있고 기존 `POST /v1/generate`에는 영향을 주지 않는다.
화면 제작·HTML 출력·이미지 생성·OCR·등록·문서 저장·부분 재생성은 실행하지 않는다.

입력 예제: [detail_page_mock.json](../examples/requests/detail_page_mock.json)
가상 머그 상품이며 사진 ID도 설명용이다. 모델 호출 0회, 추가 API 비용 0으로 구조를 검사한다.
자산 ID의 실제 존재·소유권은 아직 확인하지 않으므로 서비스 연결 시 반드시 검증해야 한다.

## 로컬에서 실행

저장소 루트에서 기존 개발 가상환경을 사용한다. 별도 키·GPU·추가 패키지는 필요 없다.

```bash
PYTHONPATH=src .venv/bin/python -m uvicorn ad_service.api.main:app --host 127.0.0.1 --port 8001
```

다른 터미널에서 같은 저장소로 이동한 다음 실행:

```bash
curl --fail-with-body http://127.0.0.1:8001/v1/mock/detail-pages \
  -H 'Content-Type: application/json' \
  --data-binary @examples/requests/detail_page_mock.json
```

`http://127.0.0.1:8001/docs`에서도 입력·출력 스키마를 확인할 수 있다.
서버는 localhost로만 열고 공용 배포하지 않는다. 기존 앱 전체의 사용자 인증·작업 접근제어는 별도 작업이다.

## 입출력 규칙

| 항목 | 이번 구현 |
|---|---|
| 버전 | `schema_version: mock-0.1`. 협의용 `draft-0.1` 예시는 받지 않음 |
| 상품 정보 | 상품 ID/버전/이름 필수. 사실·카테고리·이미지·누락 정보는 별도 필드 |
| 사실 출처 | `seller_input`, `catalog_import`만 허용. 미확인 OCR 후보는 판매자 확인 단계가 먼저 필요 |
| 이미지 | ID·역할·크기·박스. 임의 URL·로컬 파일 경로는 입력 불가 |
| 주 이미지 | 사진이 있으면 `primary_image_asset_id` 필수. 이미지 목록에 있어야 함 |
| 사진 없음 | 허용. 이미지 블록 생략. `direct_edit`는 사진이 있어야 요청 가능 |
| 선택 박스 | EXIF 방향 반영 원본 기준 정수 `[xmin,ymin,xmax,ymax]`, 원본 범위 검증 |
| 섹션 | `hero`, `features`, `specifications`, `cta`. `section_plan` 순서대로 반환, 종류 중복 불가 |
| 정보 부족 | 사실이 없으면 features/specifications를 생략하고 이유를 `review.omitted_sections`로 반환 |
| 문구 | 상품명·사실 원문과 고정 템플릿만 사용. 타깃·톤·지시는 수용하되 미적용 경고 표시 |
| 이미지 처리 | `composite`/`direct_edit` 값은 검증만 함. 반환 이미지 블록은 `reference_only` |
| 선택 단위 | `section_id`, `block_id`. 사실 목록/섹션 순서가 바뀌어도 동일 사실의 블록 ID 유지 |
| 순서/숨김 | 배열 순서가 표시 순서. 초기 `visible: true`. 편집한 상태를 받거나 저장하는 기능은 미구현 |
| 응답 상태 | `needs_review`, `persisted: false`. document_id/저장 버전을 발급하지 않음 |
| 실행 | 동기식·무상태. 작업 큐·진행률·취소·영구 idempotency 기록은 없음 |

예제 결과의 섹션/블록:

```text
sec_hero           → hero_heading, hero_image
sec_features       → features_heading, feature_material, feature_capacity, feature_color
sec_specifications → specifications_table (원본 사실 값과 fact_refs)
sec_cta            → cta_text
```

이미지 블록은 원본 자산 ID를 참조할 뿐 새 배경/합성본을 만들어낸 것이 아니다.
모든 입력 문자열은 데이터로 다룬다. 프론트에서도 텍스트를 escape해서 표시해야 한다.
실제 상품 사실이나 효능의 진실 여부를 이 mock이 검증해 주는 것은 아니다.

## 변경 가능한 제한과 미지원

현재 한국어(`ko-KR`)와 네 섹션 종류만 지원한다. 이미지 20장·사실 50개·카테고리 깊이 8 등의
상한은 서버 입력 보호용이며 UI의 장수/출시 정책을 확정한 것이 아니다. `auto` 언어,
메뉴판, 후기, 블로그, 상품등록은 이 엔드포인트에서 422로 거절한다. 알 수 없는 필드도 거절한다.
예산은 0 이상 유한 수만 허용하지만 mock에는 과금 호출이나 재시도가 없다.
수정 시 계약 버전을 올려 프론트와 함께 대응할 수 있게 한다.

## 검사

팀 전달용 요청/응답·JSON Schema·연결 체크리스트를 묶으려면 저장소 루트에서 실행한다.
기존 출력 폴더나 ZIP이 있으면 덮어쓰지 않고 중단하므로 매번 새 이름을 사용한다.

```bash
PYTHONPATH=src .venv/bin/python scripts/export_detail_page_handoff.py \
  --output data/outputs/detail-page-handoff-001
```

세 가지 요청을 mock API에 전달한 실제 응답을 내보내고, 지정한 폴더와 옆의 ZIP을 만든다.
생성 서버 코드는 ZIP에 포함하지 않는다. [팀 연결 안내](detail_page_handoff.md)를 참고한다.

```bash
PYTHONPATH=src .venv/bin/pytest -q tests/integration/test_detail_page_mock.py
```

검사 범위: 실행 예제·응답 스키마, 사실/이미지 참조, 다품목 카테고리, 누락 정보 처리,
ID 안정성·입력 불변성·결정적 응답, 잘못된 좌표/버전/언어/중복/추가 필드 거절,
모델 파이프라인 미호출 및 작업 디렉터리 무변경, 기존 API와의 OpenAPI 공존.
전체 회귀 검사는 `PYTHONPATH=src .venv/bin/pytest -q`로 실행한다.

다음 모델 작업: 이 구조를 기준으로 상품 정보 추출/확인 흐름을 검증하고 실제 문구 생성기를
연결한다. UI의 채팅 부분 수정은 안정적 블록 ID를 활용하되 버전·변경 범위 검증을 추가해야 한다.
