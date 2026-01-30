"""OpenAI streaming wrapper with metrics logging for Manus replication."""
import time
import os
from dataclasses import dataclass
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

Pricing = dict[str, float]

PRICING: dict[str, dict[str, dict[str, float]]] = {
    "gpt-4o-mini": {
        "flex": {"input": 0.55, "output": 2.20, "cached": 0.275},
        "batch": {"input": 0.60, "output": 2.40, "cached": 0.30},
        "standard": {"input": 1.10, "output": 4.40, "cached": 0.55},
    },
    "gpt-4o": {
        "flex": {"input": 2.50, "output": 10.00, "cached": 0.50},
        "batch": {"input": 2.50, "output": 10.00, "cached": 0.50},
        "standard": {"input": 5.00, "output": 15.00, "cached": 1.00},
    },
}


@dataclass
class StepMetrics:
    variant_id: str
    task_id: str
    step_idx: int
    ttft_ms: float
    e2e_ms: float
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    uncached_tokens: int
    estimated_cost_usd: float
    tool_name: str | None
    tool_success: bool
    prompt_cache_key: str


class OpenAIStreamWrapper:
    def __init__(self, model: str = "gpt-4o-mini", tier: str = "flex"):
        self.model = model
        self.tier = tier

        headers = {}
        timeout = {"flex": 900, "standard": 60, "priority": 30}.get(tier, 900)

        if tier in ("flex", "priority"):
            headers["OpenAI-Processing"] = "flex" if tier == "flex" else "auto"

        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE"),
            timeout=timeout,
            default_headers=headers
        )

    async def call(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict = "auto",
        prompt_cache_key: str = "task2-A",
        variant_id: str = "A1",
        task_id: str = "data_cleaning",
        step_idx: int = 0,
    ) -> tuple[dict, StepMetrics]:
        start_time = time.time()

        # Single non-streaming call - TTFT = E2E for non-streaming
        # This gives accurate cache metrics without double-call pollution
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=0.1,
            extra_headers={"prompt_cache_key": prompt_cache_key},
        )

        e2e_ms = (time.time() - start_time) * 1000
        ttft_ms = e2e_ms  # For non-streaming, TTFT = E2E

        usage = response.usage
        msg = response.choices[0].message

        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens

        cached_tokens = 0
        if hasattr(usage, "prompt_tokens_details"):
            details = usage.prompt_tokens_details
            cached_tokens = getattr(details, "cached_tokens", 0) if details else 0

        uncached_tokens = input_tokens - cached_tokens

        pricing = PRICING.get(self.model, {})
        tier_pricing = pricing.get(self.tier, {"input": 0.55, "output": 2.20, "cached": 0.275})
        estimated_cost_usd = (
            uncached_tokens * tier_pricing["input"] +
            cached_tokens * tier_pricing["cached"] +
            output_tokens * tier_pricing["output"]
        ) / 1e6

        tool_name = None
        if msg.tool_calls:
            tool_name = msg.tool_calls[0].function.name

        metrics = StepMetrics(
            variant_id=variant_id,
            task_id=task_id,
            step_idx=step_idx,
            ttft_ms=ttft_ms,
            e2e_ms=e2e_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            uncached_tokens=uncached_tokens,
            estimated_cost_usd=estimated_cost_usd,
            tool_name=tool_name,
            tool_success=True,
            prompt_cache_key=prompt_cache_key,
        )

        return msg, metrics
