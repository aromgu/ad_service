# Triton Inference Server

여기서 말하는 "Triton"은 **NVIDIA Triton Inference Server** — 모델을 프로덕션에서
서빙하기 위한 오픈소스 추론 서버다. (OpenAI Triton = GPU 커널 언어와는 다름. 아래 참고)

## 왜 쓰나

- FastAPI 안에서 `model.generate()`를 직접 부르면: 배치 안 됨, GPU 놀거나 터짐,
  모델 교체 시 서버 재시작 필요.
- Triton이 대신 해주는 것:
  - **동적 배칭**(dynamic batching): 여러 요청을 모아 한 번에 GPU로
  - **다중 모델 / 다중 버전** 동시 서빙, 무중단 로딩
  - **멀티 백엔드**: TensorRT, PyTorch(LibTorch), ONNX Runtime, vLLM, Python
  - HTTP/gRPC 표준 프로토콜 + Prometheus 메트릭

이 프로젝트 구조에서는 **FastAPI = 오케스트레이션/전처리/프롬프트 조립**,
**Triton = 실제 모델 추론**으로 역할을 나눈다.
`src/ad_service/models/` 의 래퍼가 Triton HTTP/gRPC 클라이언트를 호출하도록 구현하면 됨.

## 디렉터리 규칙 (model_repository)

Triton은 아래 레이아웃을 강제한다:

```
model_repository/
├── vlm/
│   ├── config.pbtxt          # 입출력 텐서 스펙, 백엔드, 배칭 설정
│   └── 1/                     # 버전 디렉터리 (숫자)
│       └── model.py           # python 백엔드면 여기, TensorRT면 model.plan 등
└── image_generator/
    ├── config.pbtxt
    └── 1/
        └── model.py
```

## 실행

```bash
# compose 로
docker compose -f docker/docker-compose.yml --profile triton up triton

# 또는 직접
docker run --gpus all --rm -p8001:8000 -p8002:8001 -p8003:8002 \
  -v $(pwd)/deploy/triton/model_repository:/models \
  nvcr.io/nvidia/tritonserver:24.05-py3 \
  tritonserver --model-repository=/models

# 상태 확인
curl localhost:8001/v2/health/ready
curl localhost:8001/v2/models/vlm/config
```

## 클라이언트

```bash
pip install tritonclient[all]
```

```python
import tritonclient.http as httpclient

client = httpclient.InferenceServerClient(url="localhost:8001")
# inputs 구성 후 client.infer("vlm", inputs=[...])
```

---

### 참고: "OpenAI Triton" (헷갈리지 말 것)

이름만 같은 다른 물건. GPU 커널을 파이썬 문법으로 작성하는 컴파일러/언어이며
(`pip install triton`), PyTorch 2.x의 `torch.compile`, vLLM, FlashAttention 등이
내부적으로 사용한다. 보통 **직접 코드를 쓸 일은 없고**, `torch>=2.2` + CUDA 환경이면
자동으로 깔려서 `torch.compile(model)` 한 줄로 혜택을 본다.
팀원이 "triton 써서 커널 최적화하자"는 맥락이면 이쪽, "모델 서빙하자"는 맥락이면
위의 Inference Server다.
