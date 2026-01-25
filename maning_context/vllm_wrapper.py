"""vLLM streaming wrapper for local inference."""
import time
from openai import AsyncOpenAI
from llm_wrapper import LLMWrapper
from openai_wrapper import StepMetrics


class VLLMStreamWrapper(LLMWrapper):
    """vLLM backend for local inference with OpenAI-compatible API."""

    def __init__(self, model: str, base_url: str = "http://localhost:8000/v1"):
        super().__init__(model)
        self.base_url = base_url
        # vLLM provides OpenAI-compatible API
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key="dummy"  # vLLM doesn't require authentication
        )

    async def call(
        self,
        messages: list[dict],
        tools: list[dict],
        prompt_cache_key: str = "vllm",
        variant_id: str = "A1",
        task_id: str = "data_cleaning",
        step_idx: int = 0,
    ) -> tuple[dict, StepMetrics]:
        """Call vLLM and return response with metrics.

        Note: vLLM doesn't support prompt caching like OpenAI, so cached_tokens
        will always be 0. This enables honest comparison between backends.
        """
        start_time = time.time()
        ttft_ms = 0.0
        chunks = []
        first_chunk = True

        # Stream the response to measure TTFT
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=0.1,
            stream=True,
        )

        async for chunk in response:
            if first_chunk:
                ttft_ms = (time.time() - start_time) * 1000
                first_chunk = False

            if chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    chunks.append(delta.content)

        e2e_ms = (time.time() - start_time) * 1000

        # Get non-streaming response for usage stats and tool calls
        non_stream_response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=0.1,
        )

        usage = non_stream_response.usage
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens

        msg = non_stream_response.choices[0].message
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
            cached_tokens=0,  # vLLM doesn't support prompt caching
            uncached_tokens=input_tokens,  # All tokens are uncached
            estimated_cost_usd=0.0,  # Local inference has no direct cost
            tool_name=tool_name,
            tool_success=True,
            prompt_cache_key=prompt_cache_key,
        )

        return msg, metrics
