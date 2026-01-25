"""Abstract base class for LLM backends."""
from abc import ABC, abstractmethod
from typing import Optional


class LLMWrapper(ABC):
    """Abstract base class for LLM backends."""

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    async def call(
        self,
        messages: list[dict],
        tools: list[dict],
        prompt_cache_key: str,
        variant_id: str,
        task_id: str,
        step_idx: int,
    ) -> tuple[dict, "StepMetrics"]:
        """Call LLM and return response with metrics."""
        pass
