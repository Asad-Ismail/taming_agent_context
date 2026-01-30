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
from config import load_config
from constitution import FROZEN_PREFIX

WORKSPACE = Path(__file__).parent / "workspace"


def create_wrapper(config: dict):
    """Create OpenAI LLM wrapper."""
    return OpenAIStreamWrapper(
        model=config["model"]["name"],
        tier=config["model"].get("tier", "flex")
    )


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
    args = parser.parse_args()

    config = load_config(args.config)

    # CLI args override config
    tier = args.tier or config["model"].get("tier", "flex")
    variant = args.variant or config["experiment"]["variant"]
    max_steps = args.max_steps or config["experiment"]["max_steps"]
    model_name = config["model"]["name"]
    threshold = config["token_optimization"]["large_output_threshold"]

    print(f"Initializing with OpenAI, {tier} tier, variant {variant}...")
    print(f"Model: {model_name}, Threshold: {threshold} chars")

    wrapper = create_wrapper(config)

    print("Creating workspace...")
    create_workspace()

    # Clean up previous run artifacts to ensure fresh start
    cleanup_paths = [
        WORKSPACE / "reports" / "quality.json",
        WORKSPACE / "data" / "clean.csv",
        WORKSPACE / "scripts" / "clean.py",
    ]
    for p in cleanup_paths:
        if p.exists():
            p.unlink()
            print(f"  Cleaned: {p.name}")

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

    # C1 variant: disable offloading to test token growth
    disable_offload = (variant == "C1")
    if disable_offload:
        print("[C1] Offloading DISABLED - expecting token growth")

    agent = AgentLoop(variant=variant, max_steps=max_steps, wrapper=wrapper,
                     large_output_threshold=threshold, disable_offload=disable_offload)

    # E2 variant: uses system prompt without recitation instructions
    if variant == "E2":
        print("[E2] Recitation instructions REMOVED from system prompt - agent won't be told to maintain todo.md")

    # D1/D2 variants: Tool masking experiment
    # D1 = Antipattern: dynamically filter tools (breaks cache)
    # D2 = Manus pattern: stable tools + tool_choice constraint (preserves cache)
    use_dynamic_tools = (variant == "D1")
    use_tool_choice_masking = (variant == "D2")
    if use_dynamic_tools:
        print("[D1] Dynamic tool filtering ENABLED - tools change based on state (breaks cache)")
    if use_tool_choice_masking:
        print("[D2] Tool choice masking ENABLED - stable tools + tool_choice constraint (Manus pattern)")

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
        # Per blog findings: UUID at system START breaks cache (0% hit rate)
        # We use FROZEN_PREFIX directly to avoid double UUID from get_prefix()
        if variant == "B1":
            import uuid
            run_uuid = str(uuid.uuid4())
            # Use FROZEN_PREFIX directly, not _build_messages() which may add its own UUID
            system_msg = f"RunID: {run_uuid}\n\n{FROZEN_PREFIX}"

            if messages:
                # Replace system message - this changes prefix, breaking cache
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

        # D1/D2: Tool masking logic
        # Simple state machine: after writing clean.py, only allow shell_run/fs_read/task_complete
        current_tools = TOOL_SCHEMAS
        current_tool_choice = "auto"
        
        if use_dynamic_tools:
            # D1 Antipattern: Filter tools based on state (changes tool schema = breaks cache)
            clean_script_exists = (Path(__file__).parent / "workspace" / "scripts" / "clean.py").exists()
            if clean_script_exists:
                # Only allow execution tools after script is written
                allowed_tools = {"shell_run", "fs_read", "task_complete"}
                current_tools = [t for t in TOOL_SCHEMAS if t["function"]["name"] in allowed_tools]
        
        if use_tool_choice_masking:
            # D2 Manus Pattern: Keep all tools, but use tool_choice to guide selection
            # This doesn't break cache since tools stay stable
            quality_json = Path(__file__).parent / "workspace" / "reports" / "quality.json"
            if quality_json.exists():
                # After validation exists, strongly suggest task_complete
                current_tool_choice = {"type": "function", "function": {"name": "task_complete"}}

        msg, metrics = await agent.wrapper.call(
            messages=messages,
            tools=current_tools,
            tool_choice=current_tool_choice,
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
