"""OpenAI prompt cache testing.

Tests cache behavior from https://asad-ismail.github.io/posts/prompt_caching/
Key findings:
1. UUID at system start breaks cache (early divergence)
2. UUID at system end breaks cache when tools present
3. UUID in user message preserves cache (late binding)
4. Prepending tools breaks more cache than appending
5. Temperature changes don't affect cache
"""
import os
import time
import uuid
import json
import asyncio
import argparse
from pathlib import Path
from dataclasses import dataclass

import yaml
from dotenv import load_dotenv
from openai import AsyncOpenAI

from tools import TOOL_SCHEMAS

load_dotenv()


@dataclass
class CallResult:
    call: int
    temp: float
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cache_pct: float
    ttft_ms: float


@dataclass 
class TestResult:
    name: str
    description: str
    calls: list[CallResult]
    avg_cache_pct: float
    avg_ttft_ms: float
    expected_cache_pct: float
    passed: bool


def create_client(tier: str = "flex") -> AsyncOpenAI:
    configs = {
        "flex": {"timeout": 900, "header": "flex"},
        "standard": {"timeout": 60, "header": None},
    }
    config = configs.get(tier, configs["flex"])
    headers = {"OpenAI-Processing": config["header"]} if config["header"] else {}
    
    return AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE"),
        timeout=config["timeout"],
        default_headers=headers
    )


class CacheTestRunner:
    USER_MESSAGES = [
        "List the files in the scripts directory.",
        "What files are in the scripts folder?",
        "Show me the contents of scripts directory."
    ]

    def __init__(self, client: AsyncOpenAI, system: str, user: str, tools: list[dict]):
        self.client = client
        self.system = system
        self.user = user
        self.tools = tools

    async def run_suite(self, suite: dict) -> TestResult:
        name = suite["name"]
        desc = suite["description"]
        iterations = suite["iterations"]
        temps = suite["temperature"]
        if not isinstance(temps, list):
            temps = [temps] * iterations
        
        calls = []
        for i in range(iterations):
            system = self._transform_system(suite["system_prompt"])
            user = self._transform_user(suite["user_message"], i)
            tools = self._transform_tools(suite["tools"])
            temp = temps[i] if i < len(temps) else temps[-1]
            
            result = await self._call_api(system, user, tools, temp, i + 1, name)
            calls.append(result)
            await asyncio.sleep(0.5)
        
        avg_cache = sum(c.cache_pct for c in calls) / len(calls)
        avg_ttft = sum(c.ttft_ms for c in calls) / len(calls)
        expected = suite["expected_cache_pct"]
        passed = avg_cache >= expected - 10
        
        return TestResult(name, desc, calls, avg_cache, avg_ttft, expected, passed)

    def _transform_system(self, op: str) -> str:
        if op == "base":
            return self.system
        if op == "prepend_uuid":
            return f"RunID: {uuid.uuid4()}\n\n{self.system}"
        if op == "append_uuid":
            return f"{self.system}\n\nRunID: {uuid.uuid4()}"
        return self.system

    def _transform_user(self, op: str, iteration: int) -> str:
        if op == "constant":
            return self.user
        if op == "append_uuid":
            return f"{self.user}\n\nRunID: {uuid.uuid4()}"
        if op == "rotate":
            return self.USER_MESSAGES[iteration % len(self.USER_MESSAGES)]
        return self.user

    def _transform_tools(self, op: str) -> list[dict]:
        if op == "constant":
            return self.tools
        if op == "none":
            return []
        if op == "prepend_new":
            new_tool = self._make_tool()
            return [new_tool] + self.tools
        if op == "append_new":
            new_tool = self._make_tool()
            return self.tools + [new_tool]
        return self.tools

    def _make_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": f"tool_{uuid.uuid4().hex[:8]}",
                "description": "Dynamic test tool",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        }

    async def _call_api(self, system: str, user: str, tools: list[dict], 
                        temp: float, call_num: int, cache_key: str) -> CallResult:
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
        cached = 0
        if hasattr(usage, 'prompt_tokens_details') and usage.prompt_tokens_details:
            cached = getattr(usage.prompt_tokens_details, 'cached_tokens', 0)
        
        cache_pct = (cached / usage.prompt_tokens * 100) if usage.prompt_tokens > 0 else 0
        
        return CallResult(
            call=call_num,
            temp=temp,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cached_tokens=cached,
            cache_pct=cache_pct,
            ttft_ms=ttft
        )


def print_result(result: TestResult):
    print(f"\n{'=' * 60}")
    print(f"{result.name}: {result.description}")
    print(f"{'=' * 60}")
    
    for c in result.calls:
        print(f"  [{c.call}] temp={c.temp} | {c.cached_tokens}/{c.input_tokens} ({c.cache_pct:.1f}%) | {c.ttft_ms:.0f}ms")
    
    status = "PASS" if result.passed else "FAIL"
    print(f"  Avg: {result.avg_cache_pct:.1f}% (expected: {result.expected_cache_pct}%) [{status}]")


def save_results(results: list[TestResult], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    
    data = {
        "total": len(results),
        "passed": sum(r.passed for r in results),
        "tests": [
            {
                "name": r.name,
                "description": r.description,
                "passed": r.passed,
                "avg_cache_pct": round(r.avg_cache_pct, 1),
                "expected_cache_pct": r.expected_cache_pct,
                "avg_ttft_ms": round(r.avg_ttft_ms, 0),
                "calls": [
                    {"call": c.call, "temp": c.temp, "input": c.input_tokens, 
                     "cached": c.cached_tokens, "cache_pct": round(c.cache_pct, 1), "ttft_ms": round(c.ttft_ms, 0)}
                    for c in r.calls
                ]
            }
            for r in results
        ]
    }
    
    with open(output_dir / "cache_test_results.json", 'w') as f:
        json.dump(data, f, indent=2)


def count_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model("gpt-4o-mini")
        return len(enc.encode(text))
    except ImportError:
        return len(text) // 4


async def main():
    parser = argparse.ArgumentParser(description="Test OpenAI prompt caching")
    parser.add_argument("--config", default="prompt_cache_config.yaml", help="Config file")
    parser.add_argument("--suite", help="Run specific suite")
    parser.add_argument("--tier", choices=["flex", "standard"], default="flex")
    parser.add_argument("--output", default="results")
    args = parser.parse_args()
    
    config_path = Path(__file__).parent / args.config
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    system = config["base_prompt"]["system"]
    user = config["base_prompt"]["user"]
    tools = TOOL_SCHEMAS
    
    sys_tokens = count_tokens(system)
    tool_tokens = count_tokens(str(tools))
    print(f"\nTokens: system={sys_tokens}, tools={tool_tokens}, total={sys_tokens + tool_tokens}")
    
    if sys_tokens + tool_tokens < 1024:
        print("Warning: < 1024 tokens, caching may not activate")
    
    suites = config["test_suites"]
    if args.suite:
        suites = [s for s in suites if s["name"] == args.suite]
        if not suites:
            print(f"Suite '{args.suite}' not found")
            return
    
    client = create_client(args.tier)
    runner = CacheTestRunner(client, system, user, tools)
    
    print(f"\n{'=' * 60}")
    print(f"PROMPT CACHE TESTS | Tier: {args.tier} | Suites: {len(suites)}")
    print(f"{'=' * 60}")
    
    results = []
    for suite in suites:
        result = await runner.run_suite(suite)
        results.append(result)
        print_result(result)
    
    output_dir = Path(args.output)
    save_results(results, output_dir)
    
    passed = sum(r.passed for r in results)
    print(f"\n{'=' * 60}")
    print(f"RESULT: {passed}/{len(results)} passed")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
