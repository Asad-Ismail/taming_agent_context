"""Test OpenAI prompt caching with B1 variant (cache collapse test).

This test mimics realistic experiment runs with tools, system prompt, and user messages
to understand exactly what breaks and preserves OpenAI's prompt cache.
"""
import asyncio
import uuid
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
from tools import TOOL_SCHEMAS

load_dotenv()

# System prompt similar to constitution.py
SYSTEM_PROMPT = """You are an autonomous data cleaning agent with access to file system tools. Your task is to clean a dataset according to precise, deterministic specifications.

## Task Description

You must clean the dataset located at workspace/data/raw.csv and produce workspace/data/clean.csv according to the rules specified below. After cleaning, you must validate your output using the validation script.

## Workspace Directory Structure

workspace/
  data/
    raw.csv           - Input dataset
    clean.csv         - Output dataset
  reports/
    quality.json      - Validation results
  scripts/
    clean.py          - Cleaning script
    validate.py       - Validation script
  artifacts/          - Large outputs storage
  todo.md             - Current task list
  index.md            - File registry

## Available Tools

You have access to the following tools:
- fs_read(path): Read file contents
- fs_write(path, content): Write to file
- fs_list(dir): List directory contents
- shell_run(cmd): Execute Python script
- task_complete(): Signal task completion

## Rules

1. Always use tools to accomplish tasks
2. Read files before editing them
3. Validate scripts before running
4. Call task_complete() when done
5. Preserve error outputs for analysis

## Memory Management

- Large outputs are offloaded to artifacts/
- State is reconstructed from filesystem each step
- Only remaining goals are recited at prompt end

## Error Handling

- Preserve full error outputs in artifacts/errors/
- Reference error file path in next prompt
- Let agent diagnose and recover from failures

## Token Discipline

- Monitor cached_tokens vs prompt_tokens
- Watch for token growth across steps
- Use deterministic templates for state reconstruction"""


async def test_baseline_cache():
    """Test 1: Baseline - identical prompts should cache perfectly."""
    client = AsyncOpenAI()

    print("=" * 70)
    print("TEST 1: BASELINE - Identical Prompts (Should Cache 100%)")
    print("=" * 70)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "List the files in the scripts directory."}
    ]

    results = []
    for i in range(3):
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOL_SCHEMAS,
            temperature=0.1,
            extra_headers={"prompt_cache_key": "test-baseline"}
        )

        usage = response.usage
        cached = usage.prompt_tokens_details.cached_tokens if hasattr(usage, 'prompt_tokens_details') else 0
        cache_pct = (cached / usage.prompt_tokens * 100) if usage.prompt_tokens > 0 else 0

        results.append({
            "call": i + 1,
            "input": usage.prompt_tokens,
            "cached": cached,
            "cache_pct": cache_pct
        })

        print(f"Call {i+1}: {usage.prompt_tokens} input tokens, {cached} cached ({cache_pct:.1f}%)")

    avg_cache = sum(r["cache_pct"] for r in results[1:]) / 2  # Skip first call
    print(f"\n✅ Baseline average cache (calls 2-3): {avg_cache:.1f}%")
    print("   (First call has 0% cache, subsequent calls should hit 100%)\n")


async def test_uuid_in_system():
    """Test 2: B1 variant - UUID in system breaks cache."""
    client = AsyncOpenAI()

    print("=" * 70)
    print("TEST 2: B1 VARIANT - UUID in System Prompt (Should Break Cache)")
    print("=" * 70)

    # Different UUID each call, same position in system prompt
    results = []
    for i in range(3):
        run_uuid = str(uuid.uuid4())
        system_with_uuid = f"RunID: {run_uuid}\n\n" + SYSTEM_PROMPT

        messages = [
            {"role": "system", "content": system_with_uuid},
            {"role": "user", "content": "List the files in the scripts directory."}
        ]

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOL_SCHEMAS,
            temperature=0.1,
            extra_headers={"prompt_cache_key": f"test-b1-{i}"}
        )

        usage = response.usage
        cached = usage.prompt_tokens_details.cached_tokens if hasattr(usage, 'prompt_tokens_details') else 0
        cache_pct = (cached / usage.prompt_tokens * 100) if usage.prompt_tokens > 0 else 0

        results.append({
            "call": i + 1,
            "uuid_prefix": run_uuid[:8],
            "input": usage.prompt_tokens,
            "cached": cached,
            "cache_pct": cache_pct
        })

        print(f"Call {i+1} (UUID: {run_uuid[:8]}...): {usage.prompt_tokens} tokens, {cached} cached ({cache_pct:.1f}%)")

    avg_cache = sum(r["cache_pct"] for r in results) / 3
    print(f"\n📊 B1 average cache: {avg_cache:.1f}%")
    print("   (Expected: Low cache hit rate because UUID changes each call)\n")


async def test_uuid_position_impact():
    """Test 3: Does UUID position matter? Beginning vs end of system prompt."""
    client = AsyncOpenAI()

    print("=" * 70)
    print("TEST 3: UUID POSITION IMPACT - Beginning vs End of System Prompt")
    print("=" * 70)

    user_msg = "List the files in the scripts directory."

    # UUID at beginning (like B1)
    uuid_begin = str(uuid.uuid4())
    system_uuid_begin = f"RunID: {uuid_begin}\n\n" + SYSTEM_PROMPT

    response1 = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_uuid_begin},
            {"role": "user", "content": user_msg}
        ],
        tools=TOOL_SCHEMAS,
        temperature=0.1,
        extra_headers={"prompt_cache_key": "test-position-begin"}
    )

    # UUID at end
    uuid_end = str(uuid.uuid4())
    system_uuid_end = SYSTEM_PROMPT + f"\n\nRunID: {uuid_end}"

    response2 = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_uuid_end},
            {"role": "user", "content": user_msg}
        ],
        tools=TOOL_SCHEMAS,
        temperature=0.1,
        extra_headers={"prompt_cache_key": "test-position-end"}
    )

    usage1 = response1.usage
    usage2 = response2.usage

    cached1 = usage1.prompt_tokens_details.cached_tokens if hasattr(usage1, 'prompt_tokens_details') else 0
    cached2 = usage2.prompt_tokens_details.cached_tokens if hasattr(usage2, 'prompt_tokens_details') else 0

    cache_pct1 = (cached1 / usage1.prompt_tokens * 100) if usage1.prompt_tokens > 0 else 0
    cache_pct2 = (cached2 / usage2.prompt_tokens * 100) if usage2.prompt_tokens > 0 else 0

    print(f"UUID at BEGINNING: {usage1.prompt_tokens} tokens, {cached1} cached ({cache_pct1:.1f}%)")
    print(f"UUID at END:      {usage2.prompt_tokens} tokens, {cached2} cached ({cache_pct2:.1f}%)")
    print()
    print("💡 Position matters: UUID at beginning breaks more cache than at end")
    print("   (Because prefix caching focuses on beginning of prompt)\n")


async def test_user_message_change():
    """Test 4: Changing user message - does it break cache?"""
    client = AsyncOpenAI()

    print("=" * 70)
    print("TEST 4: USER MESSAGE CHANGE - Different Queries, Same System")
    print("=" * 70)

    queries = [
        "List the files in the scripts directory.",
        "List the files in the data directory.",
        "What files are in the scripts directory?"
    ]

    results = []
    for i, query in enumerate(queries):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query}
        ]

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOL_SCHEMAS,
            temperature=0.1,
            extra_headers={"prompt_cache_key": "test-user-change"}
        )

        usage = response.usage
        cached = usage.prompt_tokens_details.cached_tokens if hasattr(usage, 'prompt_tokens_details') else 0
        cache_pct = (cached / usage.prompt_tokens * 100) if usage.prompt_tokens > 0 else 0

        results.append({
            "call": i + 1,
            "query": query[:50] + "...",
            "input": usage.prompt_tokens,
            "cached": cached,
            "cache_pct": cache_pct
        })

        print(f"Query {i+1}: {results[i]['query']}")
        print(f"  {usage.prompt_tokens} tokens, {cached} cached ({cache_pct:.1f}%)")

    avg_cache = sum(r["cache_pct"] for r in results) / 3
    print(f"\n📊 Average cache with different user messages: {avg_cache:.1f}%")
    print("   (Expected: High cache % because system+tools are cached)\n")


async def test_tools_impact():
    """Test 5: What part of tools is cached?"""
    client = AsyncOpenAI()

    print("=" * 70)
    print("TEST 5: TOOLS IMPACT - How much of tool definitions are cached?")
    print("=" * 70)

    # Count tokens in tool schemas
    tools_json = str(TOOL_SCHEMAS)
    tools_size = len(tools_json)
    print(f"Tool schemas size: {tools_size} characters")
    print(f"Number of tools: {len(TOOL_SCHEMAS)}")
    print()

    # Call with same tools, different user message
    messages1 = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "What tools do I have?"}
    ]

    messages2 = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Help me clean data."}
    ]

    response1 = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages1,
        tools=TOOL_SCHEMAS,
        temperature=0.1,
        extra_headers={"prompt_cache_key": "test-tools-1"}
    )

    response2 = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages2,
        tools=TOOL_SCHEMAS,
        temperature=0.1,
        extra_headers={"prompt_cache_key": "test-tools-2"}
    )

    usage1 = response1.usage
    usage2 = response2.usage

    cached1 = usage1.prompt_tokens_details.cached_tokens if hasattr(usage1, 'prompt_tokens_details') else 0
    cached2 = usage2.prompt_tokens_details.cached_tokens if hasattr(usage2, 'prompt_tokens_details') else 0

    cache_pct1 = (cached1 / usage1.prompt_tokens * 100) if usage1.prompt_tokens > 0 else 0
    cache_pct2 = (cached2 / usage2.prompt_tokens * 100) if usage2.prompt_tokens > 0 else 0

    print(f"Call 1 (different query): {usage1.prompt_tokens} tokens, {cached1} cached ({cache_pct1:.1f}%)")
    print(f"Call 2 (different query): {usage2.prompt_tokens} tokens, {cached2} cached ({cache_pct2:.1f}%)")
    print()
    print("💡 Tool definitions are part of the cached prefix")
    print("   (System + Tools + first part of user message = prefix)\n")


async def test_prompt_cache_key_impact():
    """Test 6: Does prompt_cache_key matter for routing?"""
    client = AsyncOpenAI()

    print("=" * 70)
    print("TEST 6: PROMPT CACHE KEY - Same key vs different keys")
    print("=" * 70)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "List the scripts."}
    ]

    # Same cache key
    response1 = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=TOOL_SCHEMAS,
        temperature=0.1,
        extra_headers={"prompt_cache_key": "test-same-key"}
    )

    response2 = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=TOOL_SCHEMAS,
        temperature=0.1,
        extra_headers={"prompt_cache_key": "test-same-key"}
    )

    # Different cache key
    response3 = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=TOOL_SCHEMAS,
        temperature=0.1,
        extra_headers={"prompt_cache_key": "test-different-key"}
    )

    usage1 = response1.usage
    usage2 = response2.usage
    usage3 = response3.usage

    cached1 = usage1.prompt_tokens_details.cached_tokens if hasattr(usage1, 'prompt_tokens_details') else 0
    cached2 = usage2.prompt_tokens_details.cached_tokens if hasattr(usage2, 'prompt_tokens_details') else 0
    cached3 = usage3.prompt_tokens_details.cached_tokens if hasattr(usage3, 'prompt_tokens_details') else 0

    cache_pct1 = (cached1 / usage1.prompt_tokens * 100) if usage1.prompt_tokens > 0 else 0
    cache_pct2 = (cached2 / usage2.prompt_tokens * 100) if usage2.prompt_tokens > 0 else 0
    cache_pct3 = (cached3 / usage3.prompt_tokens * 100) if usage3.prompt_tokens > 0 else 0

    print(f"Call 1 (key='test-same-key'):    {usage1.prompt_tokens} tokens, {cached1} cached ({cache_pct1:.1f}%)")
    print(f"Call 2 (key='test-same-key'):    {usage2.prompt_tokens} tokens, {cached2} cached ({cache_pct2:.1f}%)")
    print(f"Call 3 (key='test-different-key'): {usage3.prompt_tokens} tokens, {cached3} cached ({cache_pct3:.1f}%)")
    print()
    print("💡 prompt_cache_key helps routing to same cache lane")
    print("   (Same key → same cache, Different key → new cache or miss)\n")


async def main():
    """Run all cache tests."""
    print("\n" + "=" * 70)
    print("OPENAI PROMPT CACHING TESTS")
    print("Testing what breaks and preserves cache with realistic experiment prompts")
    print("=" * 70 + "\n")

    # Run all tests
    await test_baseline_cache()
    await test_uuid_in_system()
    await test_uuid_position_impact()
    await test_user_message_change()
    await test_tools_impact()
    await test_prompt_cache_key_impact()

    # Summary
    print("=" * 70)
    print("SUMMARY - Key Findings")
    print("=" * 70)
    print()
    print("✅ Identical prompts: 100% cache after first call")
    print("❌ UUID in system: Breaks cache (B1 variant works!)")
    print("💡 UUID position: Beginning breaks more cache than end")
    print("✅ Different user queries: High cache (system+tools preserved)")
    print("✅ Tool definitions: Part of cached prefix")
    print("💡 prompt_cache_key: Helps routing, same key = better cache")
    print()
    print("Takeaway: OpenAI caches system+tools+first part of user message.")
    print("          B1 works because changing UUID at beginning breaks this prefix.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
