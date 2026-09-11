# 생성 중 화면 작업 API — generation-job-0.1

`POST /v1/generate`의 동기 실행을 감싼 영속 작업 계약이다. 프론트는 이 API로 작업을 등록하고,
상태 또는 새 이벤트를 조회해 와이어프레임의 생성 중 화면을 표시한다. 기본 설정이 `mock`이면
외부 모델 호출과 비용 없이 전체 흐름을 확인할 수 있다.

## 1. 작업 등록

`POST /v1/generation-jobs`

```json
{
  "request": {
    "request_id": "seller_detail_001",
    "text": "판매할 상품 설명",
    "image_path": null,
    "outputs": ["copy", "banner", "detail_visual"],
    "options": {},
    "source": {}
  },
  "seed": 0
}
```

HTTP `202`와 `status=queued`를 반환한다. `request_id`가 작업 ID이자 결과 폴더 ID다. 동일한
요청을 다시 보내면 기존 작업을 `replayed=true`로 반환하고 모델을 다시 호출하지 않는다. 같은
ID에 다른 내용이 있거나 기존 동기 생성 결과 폴더가 있으면 HTTP `409`로 중단한다.

## 2. 상태와 이벤트 조회

- `GET /v1/generation-jobs/{job_id}`: 현재 상태 한 건
- `GET /v1/generation-jobs/{job_id}/events?after_sequence=7`: 7번 이후 이벤트
- `GET /v1/generation-jobs/{job_id}/result`: 성공한 작업의 기존 `GenerationResult`

상태는 `queued → running → succeeded | failed | cancelled`다. 실행 중 취소 요청은 외부 호출이
즉시 멈추지 않을 수 있으므로 `cancel_requested`로 따로 표시한다. 실제 단계는 다음 중 파이프라인이
진입한 항목만 순서대로 기록한다.

1. `validating_input`
2. `generating_copy`
3. `extracting_product`
4. `generating_images`
5. `compositing`
6. `validating_result`
7. `completed`

각 이벤트는 단조 증가하는 `sequence`를 가진다. 아직 신뢰할 만한 전체 작업 시간 분모가 없으므로
`progress_percent`와 `estimated_remaining_ms`는 `null`이다. 프론트는 현재 단계, 완료 이미지 수,
전체 이미지 수를 이용해 단계형 UI를 표시한다. 화면 예시의 42%나 40초를 실제 측정값처럼 쓰지 않는다.

`model_calls`, `image_generation_calls`, `preprocessing_calls`, `recorded_cost_usd`는 실행기가 실제
체크포인트에서 누적한다. 실패 응답의 `error`에는 코드, 메시지, 재시도 가능 여부가 포함된다.

## 3. 취소

`POST /v1/generation-jobs/{job_id}/cancel`

- 대기 중: 모델 호출 없이 즉시 `cancelled`
- 실행 중: `cancel_requested`로 바꾼 뒤 현재 외부 호출 다음 체크포인트에서 `cancelled`
- 성공·실패 후: HTTP `409`
- 같은 취소 재요청: 상태를 바꾸지 않고 `replayed=true`

호출이 이미 끝났다면 그때까지 기록된 호출 수와 비용은 취소 후에도 남는다.

## 4. 재시도

`POST /v1/generation-jobs/{job_id}/retry`

```json
{"new_request_id": "seller_detail_001_retry_1"}
```

취소됐거나 `error.retryable=true`인 실패만 재시도한다. 새 ID로 새 작업과 새 결과 폴더를 만들기
때문에 기존 작업 상태, 부분 파일, 성공 결과를 덮어쓰지 않는다. 입력 오류나 예산 초과처럼
`retryable=false`인 실패는 입력·설정을 수정해 새 요청으로 등록해야 한다.

## 5. 현재 실행 범위

MVP는 프로세스 안의 단일 워커로 작업을 순서대로 실행해 파일 기반 비용 원장의 동시 쓰기를 막는다.
서비스 재시작 시 대기 작업은 다시 대기열에 넣고, 실행 중이던 작업은 자동 재호출하지 않고
`worker_restarted` 실패로 확정한다. 여러 서버 인스턴스로 확장할 때는 이 계약을 유지하면서 작업 큐와
DB 저장소로 교체해야 한다.
