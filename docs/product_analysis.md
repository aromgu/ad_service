# 공통 상품 이미지 분석 모델 — product-analysis-0.1

와이어프레임의 상세페이지 자동 완성, 블로그 상품 이해, 상품등록 OCR·분류가 공유하는
첫 번째 모델 단계다. 사진을 바로 상품 사실로 저장하지 않고 `OCR`, `시각 관찰`, `추천`,
`미확인`, `판매자 입력과의 충돌`로 나누어 반환한다.

## 현재 구현

- 입력 이미지 1~8장과 판매자 입력, 분석할 field 목록을 GPT-5.4-mini에 한 번 전달한다.
- JPEG·PNG·WEBP 형식, 파일당 20MB·전체 40MB, asset ID·크기·MIME 일치를 검사한다.
- OCR·관찰 후보에는 이미지와 원본 픽셀 기준 bbox 근거를 요구한다.
- 요청하지 않은 field, 누락된 requested field, 없는 asset/candidate 참조, 범위 밖 bbox를 거부한다.
- 소재·성분·효능·가격·재고·인증·후기 등 보이지 않는 정보는 `unknown`으로 남긴다.
- 출력은 항상 `needs_review`, `persisted=false`이며 상품 DB를 자동 수정하지 않는다.
- 모델 1회, 이미지 생성 0회, 자동 재시도 0회이며 토큰·추정 비용·지연시간을 기록한다.

실제 업로드·자산 저장·소유권 검사는 서비스 파트다. 모델 모듈은 검증된 asset 메타데이터와
이미지 바이트를 전달받는다. HTTP 업로드 형식은 서비스 팀의 자산 API가 정해진 뒤 연결한다.

## 로컬/VM 실행

요청 JSON의 asset 메타데이터는 실제 파일 크기와 같아야 한다. 결과 폴더는 덮어쓰지 않는다.

```bash
PYTHONPATH=src python scripts/run_product_analysis.py \
  --request examples/requests/product_analysis.json \
  --asset front=/data/inputs/cosmetics.webp \
  --output /data/runs/cjpark/product_analysis_cosmetics_001
```

결과 폴더에는 검증된 요청, 모델 설정·이미지 SHA256, 원시 응답, 최종 결과가 저장된다.
실패 시 자동 재시도하지 않고 `failure.json`을 남긴다. API 키는 환경변수로만 전달한다.

## 구현된 다음 연결

1. `ProductApprovalRequest`가 사용자가 확인·수정한 값과 근거 후보 ID를 받는다.
2. `POST /v1/product-analysis/approve`가 승인된 값만 공통 `product.facts`로 변환한다.
3. `POST /v1/detail-pages/plan`이 같은 facts로 상세페이지 섹션 설계안을 만든다.

블로그·상품등록 모델 연결과 서비스 자산 ID를 이미지 바이트로 해석하는 내부 어댑터는 후속 작업이다.
