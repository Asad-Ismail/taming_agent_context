"""Test vLLM prefix caching with cache-breaking UUID."""
import asyncio
import uuid
from vllm_wrapper import VLLMStreamWrapper


async def test_prefix_cache_clean():
    """Test that cache is broken between runs with unique UUID."""

    wrapper = VLLMStreamWrapper(
        model="TheBloke/CodeLlama-7B-Instruct-AWQ",
        base_url="http://localhost:8000/v1"
    )

    # Generate unique UUID for THIS RUN to break cache from previous runs
    run_uuid = str(uuid.uuid4())

    print("Testing vLLM Prefix Caching with Cache-Breaking UUID")
    print("=" * 60)
    print(f"Run UUID: {run_uuid}")
    print("=" * 60)

    # System prompt with UNIQUE UUID to break cache from previous runs
    system_prompt = f"""RUN ID: {run_uuid}

You are an AI assistant with access to tools for data cleaning and validation.

Available tools:
- fs_read(path): Read file contents
- fs_write(path, content): Write to file
- fs_list(dir): List directory contents
- shell_run(command): Execute shell command
- task_complete(): Signal task completion

Rules:
1. Always use tools to accomplish tasks
2. Read files before editing them
3. Validate scripts before running
4. Call task_complete() when done
5. Preserve error outputs for analysis

Memory Management:
- Large outputs are offloaded to artifacts/
- State is reconstructed from filesystem each step
- Only remaining goals are recited at prompt end

Error Handling:
- Preserve full error outputs in artifacts/errors/
- Reference error file path in next prompt
- Let agent diagnose and recover from failures

Token Discipline:
- Monitor cached_tokens vs prompt_tokens
- Watch for token growth across steps
- Use deterministic templates for state reconstruction"""

    # Different user queries but same system prompt (with same UUID)
    queries = [
        "What tools do I have available?",
        "How should I handle errors?",
        "What are the token discipline rules?",
    ]

    print(f"\nSystem Prompt: {len(system_prompt)} chars")
    print(f"Number of queries: {len(queries)}")
    print()

    # Track previous stats
    prev_hits, prev_queries = await wrapper._get_cache_stats()
    print(f"Initial Aggregate Cache: {prev_hits:,} hits / {prev_queries:,} queries")
    print()

    results = []

    for i, query in enumerate(queries, 1):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]

        import time
        start = time.time()

        response = await wrapper.client.chat.completions.create(
            model=wrapper.model,
            messages=messages,
            temperature=0.1,
        )

        ttft_ms = (time.time() - start) * 1000
        usage = response.usage

        # Get cache stats
        curr_hits, curr_queries = await wrapper._get_cache_stats()
        delta_hits = curr_hits - prev_hits
        delta_queries = curr_queries - prev_queries

        cache_hit_rate = (delta_hits / delta_queries * 100) if delta_queries > 0 else 0
        cached_tokens = int(usage.prompt_tokens * delta_hits / delta_queries) if delta_queries > 0 else 0

        results.append({
            "query": i,
            "input_tokens": usage.prompt_tokens,
            "output_tokens": usage.completion_tokens,
            "ttft_ms": ttft_ms,
            "delta_hits": delta_hits,
            "delta_queries": delta_queries,
            "cache_hit_rate": cache_hit_rate,
            "cached_tokens": cached_tokens
        })

        print(f"Query {i}: {query}")
        print(f"  Input: {usage.prompt_tokens} tokens | TTFT: {ttft_ms:.0f}ms")
        print(f"  Delta: +{delta_hits} hits / +{delta_queries} queries")
        print(f"  Cache Hit Rate: {cache_hit_rate:.1f}% | Cached: {cached_tokens} tokens")
        print()

        # Update previous stats
        prev_hits, prev_queries = curr_hits, curr_queries

    # Summary
    print("=" * 60)
    print("SUMMARY - Within Same Run")
    print("=" * 60)

    avg_cache_hit_rate = sum(r["cache_hit_rate"] for r in results) / len(results)
    avg_ttft = sum(r["ttft_ms"] for r in results) / len(results)

    print(f"Run UUID: {run_uuid}")
    print(f"Queries: {len(results)}")
    print(f"Avg Cache Hit Rate: {avg_cache_hit_rate:.1f}%")
    print(f"Avg TTFT: {avg_ttft:.0f}ms")
    print()

    print("Per-Query Breakdown:")
    for r in results:
        print(f"  Query {r['query']}: {r['cache_hit_rate']:>5.1f}% ({r['cached_tokens']:>3}/{r['input_tokens']} cached) | TTFT: {r['ttft_ms']:>5.0f}ms")
    print()

    # Analysis
    print("=" * 60)
    print("ANALYSIS")
    print("=" * 60)

    if results[0]["cache_hit_rate"] < 10:
        print("✅ Query 1 has ~0% cache hit (expected - unique UUID breaks cache)")
    else:
        print(f"⚠️  Query 1 has {results[0]['cache_hit_rate']:.1f}% cache hit (unexpected - should be ~0%)")

    if len(results) >= 2:
        improvement = results[1]["cache_hit_rate"] - results[0]["cache_hit_rate"]
        print(f"✅ Query 2 cache hit rate increased by {improvement:.1f}% points")

    if results[1]["cache_hit_rate"] > 70:
        print(f"✅ Query 2 has high cache hit rate ({results[1]['cache_hit_rate']:.1f}%) - stable prefix working!")

    print()
    print("Re-run this script to generate a NEW UUID and verify Query 1")
    print("always has ~0% cache hit on each fresh run.")


if __name__ == "__main__":
    asyncio.run(test_prefix_cache_clean())
