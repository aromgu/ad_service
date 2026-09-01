from __future__ import annotations

import json
import os
import time
from typing import Any

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
        feature = request.features[0]
        second = request.features[1] if len(request.features) > 1 else request.category
        offer = f" {request.offer}" if request.offer else ""
        result = CopyResult(
            product_summary=(
                f"{request.product_name}은(는) {feature}을 강조한 "
                f"{request.category} 상품입니다."
            ),
            headline_candidates=[
                f"오늘은 {feature}",
                f"{second}, 한 번에 즐겨요",
                f"{request.product_name}으로 채우는 순간",
            ],
            body_candidates=[
                f"{feature}이 필요한 순간, {request.product_name}을 만나보세요.{offer}".strip(),
                f"{request.target_audience}을 위한 {second} 선택입니다.",
                f"입력 정보에 충실하게 {feature}의 매력을 전합니다.",
            ],
            cta_candidates=["자세히 보기", "지금 만나보기", "상품 확인하기"],
            keywords=[request.product_name, feature, second],
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

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("install ML dependencies with `pip install -e '.[ml]'`") from exc
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            torch_dtype="auto",
            device_map="auto",
        )

    def generate(self, request: GenerationRequest) -> CopyProviderOutput:
        self._load()
        started = time.perf_counter()
        messages = [{"role": "user", "content": build_qwen_copy_prompt(request)}]
        text = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        inputs = self._tokenizer([text], return_tensors="pt").to(self._model.device)
        output_ids = self._model.generate(**inputs, max_new_tokens=900, do_sample=False)
        generated = output_ids[0][inputs.input_ids.shape[-1] :]
        output_text = self._tokenizer.decode(generated, skip_special_tokens=True)
        value = CopyResult.model_validate(_extract_json(output_text))
        return CopyProviderOutput(
            value=value,
            metrics=ProviderMetrics(
                latency_ms=int((time.perf_counter() - started) * 1000),
                input_tokens=int(inputs.input_ids.shape[-1]),
                output_tokens=int(generated.shape[-1]),
            ),
        )
