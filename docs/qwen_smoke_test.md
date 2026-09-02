# Qwen3-8B 문구 모델 첫 실행

## 이번 단계의 목표

식료품 소매 상품 설명 한 건을 Qwen3-8B에 입력하고 광고 문구 JSON을 저장한다.
이미지 모델과 Triton은 아직 실행하지 않는다. 단독 추론이 성공한 뒤 같은 코드를
Triton에 연결한다.

## 1. GPU Docker 이미지 만들기

프로젝트 최상위 폴더에서 다음 명령을 실행한다.

```bash
docker build -f docker/Dockerfile.gpu -t ad-service:gpu .
```

처음 한 번은 PyTorch와 모델 라이브러리를 설치하므로 시간이 걸릴 수 있다.

## 2. 작업용 Docker 열기

```bash
docker run -it --rm --gpus all \
  -v "$PWD":/app -w /app \
  -v /home/data:/data \
  -v /home/data/hf-cache:/app/models/checkpoints \
  ad-service:gpu bash
```

- `-v "$PWD":/app`: 현재 코드를 Docker 안의 `/app`에서 사용한다.
- `-v /home/data:/data`: 팀 공용 데이터 폴더를 연결한다.
- `-v /home/data/hf-cache:/app/models/checkpoints`: 모델을 매번 다시 받지 않게 한다.
- `--rm`: Docker를 종료하면 컨테이너만 지운다. 연결한 코드와 데이터는 지워지지 않는다.

## 3. GPU 확인

Docker 안에서 실행한다.

```bash
python scripts/check_gpu_env.py
```

`"ready": true`, `"cuda_available": true`, GPU 이름이 출력되면 정상이다.

## 4. 무료 Mock으로 입력 형식 확인

```bash
ad-service generate \
  --input examples/requests/copy_food_retail.json \
  --copy-provider mock \
  --image-provider mock \
  --output /data/runs/cjpark/qwen_smoke_mock
```

아래 파일이 만들어지면 요청 JSON과 결과 저장 구조가 정상이다.

```text
/data/runs/cjpark/qwen_smoke_mock/copy_food_retail_001/result.json
```

## 5. Qwen3-8B 실제 실행

```bash
ad-service generate \
  --input examples/requests/copy_food_retail.json \
  --copy-provider qwen3-8b \
  --image-provider mock \
  --output /data/runs/cjpark/qwen3_8b_smoke
```

첫 실행에는 약 16GB 규모의 모델 가중치를 내려받기 때문에 오래 걸릴 수 있다. 완료 후
다음 파일에서 광고 제목·본문·CTA 후보가 각각 세 개씩 생성됐는지 확인한다.

```text
/data/runs/cjpark/qwen3_8b_smoke/copy_food_retail_001/result.json
```

## 6. GPU 메모리 확인

다른 터미널에서 다음 명령을 실행한다.

```bash
nvidia-smi
```

모델명, 실행 성공 여부, 처리 시간, 사용한 GPU와 최대 메모리를 실험 기록에 남긴다.
오류가 나면 명령 전체와 오류의 마지막 30줄을 그대로 보관한다.

## 합격 조건

- 명령이 오류 없이 끝난다.
- `result.json`이 생성된다.
- JSON 안의 `metrics.copy_model`이 `Qwen/Qwen3-8B`이다.
- 제목, 본문, CTA가 각각 정확히 세 개다.
- 입력에 없던 가격, 할인율, 효능을 만들지 않는다.
