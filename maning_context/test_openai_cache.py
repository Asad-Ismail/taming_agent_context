"""OpenAI cache testing - main entry point.

Usage:
    python test_openai_cache.py                    # Run all tests
    python test_openai_cache.py --suite baseline  # Run specific test
    python test_openai_cache.py --tier flex       # Use flex pricing
    python test_openai_cache.py --config test_cache_config.yaml
"""
import asyncio
import argparse
from pathlib import Path

from dotenv import load_dotenv

from test_cache_framework import (
    CacheTestRunner,
    PromptConfig,
    TestSuite,
    TestReporter,
    create_client
)

load_dotenv()


def load_config(config_path: str) -> tuple[PromptConfig, list[TestSuite]]:
    """Load test configuration from YAML."""
    import yaml
    import tiktoken
    from tools import TOOL_SCHEMAS

    with open(config_path) as f:
        data = yaml.safe_load(f)

    system_prompt = data["base_prompt"]["system"]
    user_message = data["base_prompt"]["user"]
    tools = TOOL_SCHEMAS

    encoding = tiktoken.encoding_for_model("gpt-4o-mini")
    system_tokens = encoding.encode(system_prompt)
    tools_tokens = encoding.encode(str(tools))

    print(f"Base system prompt: {len(system_tokens)} tokens")
    print(f"Tool schemas: {len(tools_tokens)} tokens")
    print(f"Total: {len(system_tokens) + len(tools_tokens)} tokens")

    if len(system_tokens) < 1024:
        print("⚠️  Warning: System prompt < 1024 tokens, caching may not activate")

    prompt_config = PromptConfig(
        system=system_prompt,
        user=user_message,
        tools=tools
    )

    test_suites = []
    for suite_data in data["test_suites"]:
        suite = TestSuite(**suite_data)
        test_suites.append(suite)

    return prompt_config, test_suites


async def main():
    """Run cache tests."""
    parser = argparse.ArgumentParser(description="OpenAI cache testing framework")
    parser.add_argument("--config", default="test_cache_config.yaml", help="Test configuration file")
    parser.add_argument("--suite", help="Run specific test suite only")
    parser.add_argument("--tier", choices=["flex", "standard", "batch"], default="flex", help="Pricing tier")
    parser.add_argument("--output", default="results", help="Output directory")
    args = parser.parse_args()

    prompt_config, test_suites = load_config(args.config)

    if args.suite:
        test_suites = [s for s in test_suites if s.name == args.suite]
        if not test_suites:
            print(f"❌ Test suite '{args.suite}' not found")
            return

    client = create_client(args.tier)
    runner = CacheTestRunner(client, prompt_config)

    print(f"\n{'=' * 70}")
    print("OPENAI PROMPT CACHING TESTS")
    print(f"Tier: {args.tier.upper()}")
    print(f"Test suites: {len(test_suites)}")
    print(f"{'=' * 70}\n")

    results = []
    for suite in test_suites:
        result = await runner.run_test_suite(suite)
        results.append(result)
        TestReporter.print_result(result)

    output_dir = Path(args.output)
    TestReporter.save_json(results, output_dir)

    passed = sum(r.passed for r in results)
    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {passed}/{len(results)} tests passed")
    print(f"Results saved to: {output_dir}/")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    asyncio.run(main())
