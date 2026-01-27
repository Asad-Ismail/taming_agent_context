"""OpenAI cache testing framework.

Configurable framework for testing prompt caching behavior with
systematic variations of prompts, tools, and sampling parameters.
"""
import os
import time
import uuid
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from tools import TOOL_SCHEMAS


def create_client(tier: str = "flex") -> AsyncOpenAI:
    """Create OpenAI client with tier-specific configuration."""
    tier_configs = {
        "flex": {"timeout": 900, "header": "flex"},
        "standard": {"timeout": 60, "header": None},
        "batch": {"timeout": 900, "header": "auto"},
    }

    config = tier_configs.get(tier, tier_configs["flex"])
    headers = {}

    if config["header"]:
        headers["OpenAI-Processing"] = config["header"]

    return AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE"),
        timeout=config["timeout"],
        default_headers=headers
    )


@dataclass
class PromptConfig:
    """Base prompt configuration."""
    system: str
    user: str
    tools: list[dict]


@dataclass
class TestSuite:
    """Test suite configuration from YAML."""
    name: str
    description: str
    type: str
    iterations: int
    system_prompt: str
    user_message: str
    tools: str
    temperature: float | list[float]
    expected_cache_pct: float


@dataclass
class CallResult:
    """Result from a single API call."""
    call_number: int
    temperature: float
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cache_pct: float
    ttft_ms: float
    e2e_ms: float
    cost_usd: float
    content_preview: str
    tool_calls: list[str]


@dataclass
class TestResult:
    """Results from running a test suite."""
    suite_name: str
    suite_type: str
    calls: list[CallResult]
    avg_cache_pct: float
    avg_ttft_ms: float
    time_saved_pct: float
    total_cost_usd: float
    passed: bool


class PromptTransformer:
    """Applies transformations to prompts."""

    PADDING = " ".join(["stabilizing_prefix_context_block"] * 80)

    @staticmethod
    def prepend_uuid(prompt: str) -> tuple[str, str]:
        """Prepend UUID to prompt."""
        run_id = str(uuid.uuid4())
        return f"RunID: {run_id}\n\n{prompt}", run_id

    @staticmethod
    def append_uuid(prompt: str) -> tuple[str, str]:
        """Append UUID to prompt."""
        run_id = str(uuid.uuid4())
        return f"{prompt}\n\nRunID: {run_id}", run_id

    @staticmethod
    def prepend_padding(prompt: str) -> str:
        """Prepend padding text."""
        return f"{PromptTransformer.PADDING}\n{prompt}"

    @staticmethod
    def noop(prompt: str) -> str:
        """No transformation."""
        return prompt


class ToolTransformer:
    """Applies transformations to tool lists."""

    @staticmethod
    def noop(tools: list[dict]) -> list[dict]:
        """No transformation."""
        return tools

    @staticmethod
    def prepend_tool(tools: list[dict]) -> list[dict]:
        """Prepend a new tool with random name."""
        new_tool = {
            "type": "function",
            "function": {
                "name": f"tool_{uuid.uuid4().hex[:8]}",
                "description": "A dynamically added tool for testing",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
        return [new_tool] + tools

    @staticmethod
    def append_tool(tools: list[dict]) -> list[dict]:
        """Append a new tool with random name."""
        new_tool = {
            "type": "function",
            "function": {
                "name": f"tool_{uuid.uuid4().hex[:8]}",
                "description": "A dynamically added tool for testing",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
        return tools + [new_tool]

    @staticmethod
    def empty(tools: list[dict]) -> list[dict]:
        """Return empty tool list."""
        return []


class MessageRotator:
    """Rotates through different user messages."""

    MESSAGES = [
        "List the files in the scripts directory.",
        "What files are in the scripts folder?",
        "Show me the contents of scripts directory."
    ]

    @staticmethod
    def get_message(iteration: int) -> str:
        """Get message for this iteration."""
        return MessageRotator.MESSAGES[iteration % len(MessageRotator.MESSAGES)]


class CacheTestRunner:
    """Executes cache tests and aggregates results."""

    def __init__(self, client: AsyncOpenAI, config: PromptConfig):
        self.client = client
        self.config = config
        self.results: list[TestResult] = []

    async def run_test_suite(self, suite: TestSuite) -> TestResult:
        """Run a single test suite."""
        calls = []

        temps = suite.temperature if isinstance(suite.temperature, list) else [suite.temperature] * suite.iterations

        for i in range(suite.iterations):
            temp = temps[i] if i < len(temps) else temps[-1]

            system = self._transform_system(suite.system_prompt, i)
            user = self._transform_user(suite.user_message, i)
            tools = self._transform_tools(suite.tools, i)

            result = await self._make_call(system, user, tools, temp, i + 1, suite.name)
            calls.append(result)

        avg_cache = sum(c.cache_pct for c in calls) / len(calls)
        avg_ttft = sum(c.ttft_ms for c in calls) / len(calls)
        time_saved = ((calls[0].ttft_ms - avg_ttft) / calls[0].ttft_ms) * 100 if len(calls) > 1 else 0
        total_cost = sum(c.cost_usd for c in calls)
        passed = avg_cache >= suite.expected_cache_pct - 5

        return TestResult(
            suite_name=suite.name,
            suite_type=suite.type,
            calls=calls,
            avg_cache_pct=avg_cache,
            avg_ttft_ms=avg_ttft,
            time_saved_pct=time_saved,
            total_cost_usd=total_cost,
            passed=passed
        )

    def _transform_system(self, operation: str, iteration: int) -> str:
        """Apply transformation to system prompt."""
        transformers = {
            "base": PromptTransformer.noop,
            "prepend_uuid": PromptTransformer.prepend_uuid,
            "append_uuid": PromptTransformer.append_uuid,
        }
        fn = transformers.get(operation, PromptTransformer.noop)
        result = fn(self.config.system)
        return result[0] if isinstance(result, tuple) else result

    def _transform_user(self, operation: str, iteration: int) -> str:
        """Apply transformation to user message."""
        if operation == "constant":
            return self.config.user
        elif operation == "rotate":
            return MessageRotator.get_message(iteration)
        elif operation == "append_uuid":
            base = self.config.user
            run_id = str(uuid.uuid4())
            return f"{base}\n\nRunID: {run_id}"
        return self.config.user

    def _transform_tools(self, operation: str, iteration: int) -> list[dict]:
        """Apply transformation to tools."""
        transformers = {
            "constant": ToolTransformer.noop,
            "none": ToolTransformer.empty,
            "prepend_new_tool": ToolTransformer.prepend_tool,
            "append_new_tool": ToolTransformer.append_tool,
        }
        fn = transformers.get(operation, ToolTransformer.noop)
        return fn(self.config.tools.copy())

    async def _make_call(self, system: str, user: str, tools: list[dict], temp: float, call_num: int, cache_key: str) -> CallResult:
        """Make single API call and capture metrics."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]

        start = time.time()
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools if tools else None,
            temperature=temp,
            extra_headers={"prompt_cache_key": cache_key}
        )
        ttft = (time.time() - start) * 1000

        usage = response.usage
        cached = usage.prompt_tokens_details.cached_tokens if hasattr(usage, 'prompt_tokens_details') else 0

        msg = response.choices[0].message
        tool_calls = [tc.function.name for tc in msg.tool_calls] if msg.tool_calls else []
        content_preview = msg.content[:100] if msg.content else f"Tools: {', '.join(tool_calls)}"

        return CallResult(
            call_number=call_num,
            temperature=temp,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cached_tokens=cached,
            cache_pct=(cached / usage.prompt_tokens * 100) if usage.prompt_tokens > 0 else 0,
            ttft_ms=ttft,
            e2e_ms=ttft,
            cost_usd=0,
            content_preview=content_preview,
            tool_calls=tool_calls
        )


class TestReporter:
    """Generates test reports and summaries."""

    @staticmethod
    def print_result(result: TestResult):
        """Print test result to console."""
        print(f"\n{'=' * 70}")
        print(f"TEST: {result.suite_name}")
        print(f"{'=' * 70}")
        print(f"Description: {result.suite_type}")
        print(f"Passed: {result.passed}")

        for call in result.calls:
            print(f"  Call {call.call_number} (temp={call.temperature}):")
            print(f"    Tokens: {call.input_tokens} in, {call.output_tokens} out")
            print(f"    Cache: {call.cached_tokens}/{call.input_tokens} ({call.cache_pct:.1f}%)")
            print(f"    Timing: TTFT={call.ttft_ms:.0f}ms")
            print(f"    {call.content_preview}")

        print(f"\nSummary:")
        print(f"  Avg cache: {result.avg_cache_pct:.1f}%")
        print(f"  Avg TTFT: {result.avg_ttft_ms:.0f}ms")
        print(f"  Time saved: {result.time_saved_pct:+.1f}%")
        print(f"  Cost: ${result.total_cost_usd:.4f}")

    @staticmethod
    def save_json(results: list[TestResult], output_dir: Path):
        """Save results as JSON."""
        output_dir.mkdir(parents=True, exist_ok=True)

        for result in results:
            result_file = output_dir / "per_test_results" / f"{result.suite_name}.json"
            result_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "suite_name": result.suite_name,
                "suite_type": result.suite_type,
                "avg_cache_pct": result.avg_cache_pct,
                "avg_ttft_ms": result.avg_ttft_ms,
                "time_saved_pct": result.time_saved_pct,
                "total_cost_usd": result.total_cost_usd,
                "passed": result.passed,
                "calls": [
                    {
                        "call": c.call_number,
                        "temperature": c.temperature,
                        "input_tokens": c.input_tokens,
                        "output_tokens": c.output_tokens,
                        "cached_tokens": c.cached_tokens,
                        "cache_pct": c.cache_pct,
                        "ttft_ms": c.ttft_ms,
                        "cost_usd": c.cost_usd,
                        "content_preview": c.content_preview,
                        "tool_calls": c.tool_calls
                    }
                    for c in result.calls
                ]
            }

            with open(result_file, 'w') as f:
                json.dump(data, f, indent=2)

        summary_file = output_dir / "summary.json"
        summary = {
            "total_tests": len(results),
            "passed": sum(r.passed for r in results),
            "results": [
                {
                    "name": r.suite_name,
                    "type": r.suite_type,
                    "passed": r.passed,
                    "avg_cache_pct": r.avg_cache_pct,
                    "time_saved_pct": r.time_saved_pct
                }
                for r in results
            ]
        }

        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
