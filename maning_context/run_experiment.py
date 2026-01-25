"""Main entry point for Manus replication experiment."""
import asyncio
import argparse
import json
from pathlib import Path

from data.create_workspace import create_workspace
from data.download_and_prepare_uci_data import main as download_data
from agent_loop import AgentLoop
from tools import TOOL_SCHEMAS
from metrics import log_step_metrics, write_run_summary, print_summary
from openai_wrapper import OpenAIStreamWrapper
from vllm_wrapper import VLLMStreamWrapper
from config import load_config

WORKSPACE = Path(__file__).parent / "workspace"


def create_wrapper(backend: str, config: dict, vllm_url: str = None):
    """Factory function to create LLM wrapper based on backend."""
    if backend == "openai":
        return OpenAIStreamWrapper(
            model=config["model"]["name"],
            tier=config["model"]["tier"]
        )
    elif backend == "vllm":
        return VLLMStreamWrapper(
            model=config["model"]["name"],
            base_url=vllm_url or config.get("vllm", {}).get("base_url", "http://localhost:8000/v1")
        )
    else:
        raise ValueError(f"Unknown backend: {backend}. Choose from: openai, vllm")


async def main():
    parser = argparse.ArgumentParser(description="Run Manus replication experiment")
    parser.add_argument("--config", default=None,
                        help="Path to config YAML file (default: config.yaml)")
    parser.add_argument("--tier", choices=["flex", "standard", "batch"], default=None,
                        help="OpenAI pricing tier (overrides config)")
    parser.add_argument("--variant", default=None,
                        help="Variant identifier (overrides config)")
    parser.add_argument("--max-steps", type=int, default=None,
                        help="Maximum steps (overrides config)")
    parser.add_argument("--backend", choices=["openai", "vllm"], default=None,
                        help="LLM backend to use (openai or vllm)")
    parser.add_argument("--vllm-url", default=None,
                        help="vLLM server URL (e.g., http://localhost:8000/v1)")
    args = parser.parse_args()

    config = load_config(args.config)

    # CLI args override config
    tier = args.tier or config["model"].get("tier", "flex")
    variant = args.variant or config["experiment"]["variant"]
    max_steps = args.max_steps or config["experiment"]["max_steps"]
    backend = args.backend or config["model"].get("backend", "openai")
    vllm_url = args.vllm_url
    model_name = config["model"]["name"]
    threshold = config["token_optimization"]["large_output_threshold"]

    print(f"Initializing with {backend} backend, {tier} tier, variant {variant}...")
    if backend == "vllm":
        url = vllm_url or config.get("vllm", {}).get("base_url", "http://localhost:8000/v1")
        print(f"vLLM URL: {url}")
    print(f"Model: {model_name}, Threshold: {threshold} chars")

    wrapper = create_wrapper(backend, config, vllm_url)

    print("Creating workspace...")
    create_workspace()

    print("Downloading and preparing UCI dataset...")
    download_data()

    validate_src = Path(__file__).parent / "scripts" / "validate.py"
    validate_dst = WORKSPACE / "scripts" / "validate.py"
    if not validate_dst.exists():
        print("\nCopying validation script to workspace...")
        import shutil
        shutil.copy(validate_src, validate_dst)

    print(f"\nStarting {variant} experiment with {tier} tier...")
    print("=" * 60)

    agent = AgentLoop(variant=variant, max_steps=max_steps, wrapper=wrapper,
                     large_output_threshold=threshold)

    # Initialize messages
    state_snapshot = agent._build_state_snapshot()
    if variant == "B1":
        # For B1, will regenerate system message with fresh UUID each step
        messages = []
    else:
        # For other variants, initialize once
        messages = agent._build_messages(state_snapshot)

    for step in range(agent.max_steps):
        task_signaled_complete = False

        # For B1 variant, regenerate system message with fresh UUID each step
        if variant == "B1":
            import uuid
            run_uuid = str(uuid.uuid4())
            base_prefix = agent._build_messages(state_snapshot)[0]["content"]
            system_msg = f"RunID: {run_uuid}\n\n" + base_prefix
            print(f"[B1 DEBUG] Step {step + 1}: System prefix starts with RunID: {run_uuid[:8]}...")
            print(f"[B1 DEBUG] Full prefix length: {len(system_msg)} chars")

            if messages:
                # Replace system message in existing messages
                messages[0] = {"role": "system", "content": system_msg}
            else:
                # First step - create initial messages
                workspace_dir = Path(__file__).parent / "workspace"
                todo_content = (workspace_dir / "todo.md").read_text()
                messages = [{"role": "system", "content": system_msg},
                           {"role": "user", "content": f"{state_snapshot}\n\nCurrent todo.md:\n{todo_content}"}]

        if agent._check_success():
            print(f"\nTask completed successfully at step {step}!")
            break

        msg, metrics = await agent.wrapper.call(
            messages=messages,
            tools=TOOL_SCHEMAS,
            prompt_cache_key=f"task2-{variant[0]}",
            variant_id=variant,
            task_id="data_cleaning",
            step_idx=step,
        )

        log_step_metrics(metrics)
        agent.metrics.append(metrics)

        print(f"Step {step + 1}: TTFT={metrics.ttft_ms:.0f}ms, "
              f"In={metrics.input_tokens}, Out={metrics.output_tokens}, "
              f"Cached={metrics.cached_tokens}")

        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                result, success = agent._execute_tool(tool_name, arguments)
                result = agent._offload_large_output(result, tool_name)

                if tool_name == "task_complete":
                    task_signaled_complete = True
                    print(f"[COMPLETE] Agent signaled task completion at step {step + 1}")

                metrics.tool_name = tool_name
                metrics.tool_success = success

                print(f"  -> {tool_name}: {success}")

                # Append assistant message with tool call
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call.model_dump()]
                })
                # Append tool result message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

            if task_signaled_complete:
                print(f"[SUCCESS] Agent terminated at step {step + 1} (task_complete called)")
                break

            if agent._check_success():
                print(f"\nTask completed successfully at step {step + 1}!")
                break
        else:
            # Append assistant response (no tool calls)
            messages.append({"role": "assistant", "content": msg.content or ""})
            if msg.content:
                print(f"  Assistant: {msg.content[:100]}...")

        # NO message rebuilding - let history accumulate naturally
        # This preserves tool call results across iterations

    total_cost = sum(m.estimated_cost_usd for m in agent.metrics)
    avg_ttft = sum(m.ttft_ms for m in agent.metrics[1:]) / max(1, len(agent.metrics) - 1)
    cache_hit_ratio = sum(m.cached_tokens for m in agent.metrics) / max(1, sum(m.input_tokens for m in agent.metrics))

    summary = {
        "variant": variant,
        "tier": tier,
        "total_steps": len(agent.metrics),
        "success": agent._check_success(),
        "total_cost_usd": round(total_cost, 4),
        "avg_ttft_ms": round(avg_ttft, 2) if agent.metrics else 0,
        "max_input_tokens": max((m.input_tokens for m in agent.metrics), default=0),
        "total_input_tokens": sum(m.input_tokens for m in agent.metrics),
        "cache_hit_ratio": round(cache_hit_ratio, 3) if agent.metrics else 0,
    }

    write_run_summary(summary)
    print_summary(summary)

    return summary


if __name__ == "__main__":
    asyncio.run(main())
