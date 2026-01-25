"""vLLM streaming wrapper for local inference."""
import time
import httpx
from openai import AsyncOpenAI
from llm_wrapper import LLMWrapper
from openai_wrapper import StepMetrics


class VLLMStreamWrapper(LLMWrapper):
    """vLLM backend for local inference with OpenAI-compatible API."""

    def __init__(self, model: str, base_url: str = "http://localhost:8000/v1"):
        super().__init__(model)
        self.base_url = base_url
        # Derive metrics URL from base_url (replace /v1 with empty or /metrics)
        self.metrics_url = base_url.replace("/v1", "").rstrip("/") + "/metrics"
        # Track previous cache stats to calculate per-request deltas
        self._prev_hits = 0
        self._prev_queries = 0
        # vLLM provides OpenAI-compatible API
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key="dummy"  # vLLM doesn't require authentication
        )

    async def _get_cache_stats(self) -> tuple[int, int]:
        """Fetch prefix cache stats from vLLM /metrics endpoint.

        Returns:
            (hits, queries) - Counter values for prefix cache hits and queries
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self.metrics_url)
                response.raise_for_status()

                hits = 0
                queries = 0

                for line in response.text.split('\n'):
                    line = line.strip()
                    # Parse Prometheus counter format: vllm:prefix_cache_hits_total{...} N
                    if line and not line.startswith('#'):
                        if 'vllm:prefix_cache_hits_total{' in line:
                            parts = line.split('}')
                            if len(parts) >= 2:
                                try:
                                    hits = int(float(parts[1].strip()))
                                except (ValueError, IndexError):
                                    pass
                        elif 'vllm:prefix_cache_queries_total{' in line:
                            parts = line.split('}')
                            if len(parts) >= 2:
                                try:
                                    queries = int(float(parts[1].strip()))
                                except (ValueError, IndexError):
                                    pass

                return hits, queries
        except Exception as e:
            # Silently fall back to zeros if metrics endpoint is unavailable
            return 0, 0

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

        Fetches aggregate cache stats from /metrics endpoint and calculates
        per-request cached tokens based on prefix cache hit rate.
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

        # Fetch prefix cache stats from /metrics endpoint
        current_hits, current_queries = await self._get_cache_stats()

        # Calculate deltas (per-request values)
        delta_hits = max(0, current_hits - self._prev_hits)
        delta_queries = max(0, current_queries - self._prev_queries)

        # Update previous values for next call
        self._prev_hits = current_hits
        self._prev_queries = current_queries

        # Estimate cached tokens based on cache hit rate
        # If we have query data, estimate cached tokens proportionally
        cached_tokens = 0
        if delta_queries > 0:
            cache_hit_rate = delta_hits / delta_queries
            cached_tokens = int(input_tokens * cache_hit_rate)

        uncached_tokens = input_tokens - cached_tokens

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
            estimated_cost_usd=0.0,  # Local inference has no direct cost
            tool_name=tool_name,
            tool_success=True,
            prompt_cache_key=prompt_cache_key,
        )

        return msg, metrics
