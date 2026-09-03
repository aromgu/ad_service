from __future__ import annotations

import json
import os
import time
from typing import Any

from pydantic import ValidationError

from ad_service.api.schemas.generation import COPY_JSON_SCHEMA, CopyResult, GenerationRequest
from ad_service.models.base import CopyProvider, CopyProviderOutput, ProviderMetrics
from ad_service.prompts.templates import (
    COPY_INSTRUCTIONS,
    build_copy_prompt,
    build_qwen_copy_prompt,
)

TEXT_PRICES_PER_MILLION = {
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
}


def _extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1]
        value = value.rsplit("```", 1)[0]
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("model output did not contain a JSON object")
    return json.loads(value[start : end + 1])


class MockCopyProvider(CopyProvider):
    name = "mock-copy-v1"

    def generate(self, request: GenerationRequest) -> CopyProviderOutput:
        # Mock 모델은 API 비용 없이 파이프라인 연결을 확인하기 위한 가짜 모델입니다.
        # 실제 광고 품질 평가에는 사용하지 않고, 입력 문장의 일부만 이용해 결과를 만듭니다.
        description = request.text or "입력 이미지의 상품"
        # 미리보기 문구도 실제 평가 규칙에 가깝게 짧게 제한합니다.
        short_description = description[:12].rstrip()
        audience = request.options.target_audience or "상품을 찾는 고객"
        offer = f" {request.options.offer}" if request.options.offer else ""
        result = CopyResult(
            product_summary=f"입력된 설명을 바탕으로 소개하는 상품입니다: {description}",
            headline_candidates=[
                f"오늘 만나는 {short_description}",
                "필요한 순간, 좋은 선택",
                "일상에 더하는 새로운 가치",
            ],
            body_candidates=[
                f"입력한 특징을 담은 상품을 지금 확인해보세요.{offer}".strip(),
                f"{audience}에게 어울리는 선택입니다.",
                "입력 정보에 충실하게 상품의 매력을 전합니다.",
            ],
            cta_candidates=["자세히 보기", "지금 만나보기", "상품 확인하기"],
            keywords=[short_description, audience, request.options.tone or "광고"],
            warnings=["모의 공급자 결과이며 실제 모델 비교 점수에는 사용하지 마세요."],
        )
        return CopyProviderOutput(value=result, metrics=ProviderMetrics(latency_ms=1))


class OpenAICopyProvider(CopyProvider):
    def __init__(self, model: str = "gpt-5.4-mini", api_key: str | None = None) -> None:
        self.model = model
        self.name = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAICopyProvider")

    def generate(self, request: GenerationRequest) -> CopyProviderOutput:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("install runtime dependencies with `pip install -e .`") from exc

        started = time.perf_counter()
        client = OpenAI(api_key=self.api_key)
        response = client.responses.create(
            model=self.model,
            instructions=COPY_INSTRUCTIONS,
            input=build_copy_prompt(request),
            reasoning={"effort": "low"},
            text={
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": "ad_copy",
                    "strict": True,
                    "schema": COPY_JSON_SCHEMA,
                },
            },
            store=False,
        )
        value = CopyResult.model_validate_json(response.output_text)
        usage = response.usage
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        input_price, output_price = TEXT_PRICES_PER_MILLION.get(self.model, (0.0, 0.0))
        cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
        return CopyProviderOutput(
            value=value,
            metrics=ProviderMetrics(
                latency_ms=int((time.perf_counter() - started) * 1000),
                estimated_cost_usd=cost,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                raw={"response_id": response.id},
            ),
        )


class QwenCopyProvider(CopyProvider):
    name = "Qwen/Qwen3-8B"

    def __init__(self, model_id: str = "Qwen/Qwen3-8B") -> None:
        self.model_id = model_id
        self._model: Any = None
        self._tokenizer: Any = None
        self._load_latency_ms = 0
        self._model_vram_mb: float | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        load_started = time.perf_counter()
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("install ML dependencies with `pip install -e '.[ml]'`") from exc
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            torch_dtype="auto",
            device_map="auto",
        )
        self._load_latency_ms = int((time.perf_counter() - load_started) * 1000)

        # 모델을 GPU에 올린 직후 사용 중인 메모리를 기록합니다.
        # CPU에서 실행하는 경우에는 측정할 GPU가 없으므로 None으로 둡니다.
        if torch.cuda.is_available():
            self._model_vram_mb = round(torch.cuda.memory_allocated() / (1024**2), 1)

    def generate(self, request: GenerationRequest) -> CopyProviderOutput:
        self._load()
        import torch

        # 이전 작업의 최고 메모리 기록을 지운 뒤 이번 생성에서 사용한 최대치를 측정합니다.
        # 이미 GPU에 올라간 모델 메모리까지 포함되므로 L4에서 실행 가능한지 판단하기 쉽습니다.
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        total_input_tokens = 0
        total_output_tokens = 0
        validation_error: ValueError | ValidationError | None = None

        # 첫 출력이 JSON 또는 길이 규칙을 어기면 오류 내용을 알려주고 한 번만 다시 요청합니다.
        # 무한 재시도를 막아 GPU 시간과 서비스 응답 시간이 예측 가능하도록 합니다.
        for attempt in range(2):
            prompt = build_qwen_copy_prompt(request)
            if validation_error is not None:
                prompt += (
                    "\n\n이전 출력이 다음 검증을 통과하지 못했습니다:\n"
                    f"{validation_error}\n"
                    "사실과 글자 수를 다시 확인하고 올바른 JSON 객체만 출력하세요."
                )
            messages = [{"role": "user", "content": prompt}]
            text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            inputs = self._tokenizer([text], return_tensors="pt").to(self._model.device)
            output_ids = self._model.generate(**inputs, max_new_tokens=900, do_sample=False)
            generated = output_ids[0][inputs.input_ids.shape[-1] :]
            total_input_tokens += int(inputs.input_ids.shape[-1])
            total_output_tokens += int(generated.shape[-1])
            output_text = self._tokenizer.decode(generated, skip_special_tokens=True)
            try:
                value = CopyResult.model_validate(_extract_json(output_text))
            except (ValueError, ValidationError) as exc:
                validation_error = exc
                continue
            peak_vram_mb = None
            if torch.cuda.is_available():
                peak_vram_mb = round(torch.cuda.max_memory_allocated() / (1024**2), 1)
            return CopyProviderOutput(
                value=value,
                metrics=ProviderMetrics(
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    raw={
                        "retry_count": attempt,
                        "load_latency_ms": self._load_latency_ms,
                        "model_vram_mb": self._model_vram_mb,
                        "peak_vram_mb": peak_vram_mb,
                    },
                ),
            )

        raise RuntimeError(f"Qwen output validation failed after one retry: {validation_error}")
