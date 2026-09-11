# 상세페이지 섹션 계획 모델 — detail-plan-0.1

상품 분석 후보를 바로 콘텐츠로 쓰지 않는다. `ProductApprovalRequest`에서 사용자가 확인하거나
고친 값만 `ProductInput`으로 변환한 뒤, 그 사실을 근거로 긴 상세페이지의 섹션 설계안을 만든다.

## 처리 흐름

1. `POST /v1/product-analysis/approve`: 승인된 후보와 수정값만 공통 상품 사실로 변환
2. `POST /v1/detail-pages/plan`: 상품 사실 → 섹션 순서·목적·레이아웃·카피/이미지 작업 지시
3. 후속 카피·이미지 생성기는 각 섹션의 `fact_refs`와 `source_asset_ids` 안에서만 작업
4. 생성 결과는 에디터에서 사람 검수 후 서비스가 저장

이 단계는 최종 카피, 이미지, HTML을 만들지 않는다. 반환된 `sections[]`는 프론트 템플릿이
렌더링할 구조이며, `section_id`가 이후 챗봇 부분 수정의 안정적인 대상 ID가 된다.

## 안전 규칙

- 분석 결과 전체가 아니라 판매자가 명시적으로 승인한 값만 사실로 승격한다.
- 정보 섹션은 하나 이상의 `fact_refs`가 있어야 한다.
- 존재하지 않는 사실·이미지 참조, 중복 섹션, 섹션 수 초과를 코드에서 거부한다.
- 누락 정보는 질문 또는 섹션 생략으로 처리하고 가격·효능·성분·인증·후기를 추측하지 않는다.
- GPT-5.4-mini 한 번만 호출하며 이미지 분석·이미지 생성 호출은 0회다.
- 입력 문자 수와 최대 출력 토큰을 이용한 보수적 비용 상한이 예산보다 크면 호출 전에 중단한다.
- 자동 재시도와 문서 저장은 하지 않는다.

## 생성 중 화면에 전달할 단계

실행기는 콜백과 최종 결과의 `events[]`에 아래 실제 사건을 순서대로 기록한다.

- `input_validation`
- `seller_confirmation`
- `section_planning`
- `result_validation`

각 이벤트에는 증가하는 `sequence`와 실측 `elapsed_ms`가 있다. 정확한 진행률과 남은 시간을
계산하지 못하므로 `progress_percent`, `estimated_remaining_ms`는 `null`이다. 프론트는 이를
단계형 상태로 표시하고 임의의 42% 또는 남은 시간을 만들지 않는다.

## 로컬 실행

```bash
PYTHONPATH=src .venv/bin/python scripts/run_detail_page_plan.py \
  --request examples/requests/detail_page_plan.json \
  --output data/runs/detail_page_plan_001
```

결과 폴더에는 요청, 실행 설정, 원시 모델 응답, 단계 이벤트, 검증된 결과를 분리해 남긴다.
예제 상품 사실은 연결 테스트용 가상 머그 정보다.
