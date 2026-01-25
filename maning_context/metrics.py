"""Metrics logging and analysis for Manus replication."""
import csv
import json
from pathlib import Path
from openai_wrapper import StepMetrics

WORKSPACE = Path(__file__).parent / "workspace"


def log_step_metrics(metrics: StepMetrics):
    metrics_file = WORKSPACE / "metrics" / "run_steps.csv"

    file_exists = metrics_file.exists()

    with open(metrics_file, "a") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "variant_id", "task_id", "step_idx", "ttft_ms", "e2e_ms",
                "input_tokens", "output_tokens", "cached_tokens", "uncached_tokens",
                "estimated_cost_usd", "tool_name", "tool_success", "prompt_cache_key"
            ])

        writer.writerow([
            metrics.variant_id,
            metrics.task_id,
            metrics.step_idx,
            metrics.ttft_ms,
            metrics.e2e_ms,
            metrics.input_tokens,
            metrics.output_tokens,
            metrics.cached_tokens,
            metrics.uncached_tokens,
            metrics.estimated_cost_usd,
            metrics.tool_name or "",
            metrics.tool_success,
            metrics.prompt_cache_key,
        ])


def write_run_summary(summary: dict):
    summary_file = WORKSPACE / "metrics" / "run_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2))


def compute_red_flags(metrics_file: Path) -> dict:
    red_flags = {
        "prefix_changing": False,
        "history_leakage": False,
        "nondeterministic_rebuild": False,
    }

    if not metrics_file.exists():
        return red_flags

    with open(metrics_file) as f:
        reader = csv.DictReader(f)
        steps = list(reader)

    if len(steps) < 3:
        return red_flags

    cached_tokens = [int(s.get("cached_tokens", 0)) for s in steps[1:]]
    input_tokens = [int(s["input_tokens"]) for s in steps]
    ttft_ms = [float(s["ttft_ms"]) for s in steps]

    if sum(cached_tokens) == 0:
        red_flags["prefix_changing"] = True

    input_tokens_steps = input_tokens[1:]
    if input_tokens_steps[-1] > input_tokens_steps[0] * 1.2:
        red_flags["history_leakage"] = True

    avg_ttft = sum(ttft_ms[1:]) / len(ttft_ms[1:])
    ttft_variance = sum((x - avg_ttft) ** 2 for x in ttft_ms[1:]) / len(ttft_ms[1:])
    if ttft_variance > 10000:
        red_flags["nondeterministic_rebuild"] = True

    return red_flags


def print_summary(summary: dict):
    print("\n" + "=" * 60)
    print(f"RUN SUMMARY - Variant {summary['variant']}")
    print("=" * 60)
    print(f"Success: {summary['success']}")
    print(f"Total Steps: {summary['total_steps']}")
    print(f"Total Cost: ${summary['total_cost_usd']:.4f}")
    print(f"Avg TTFT (steps 2+): {summary['avg_ttft_ms']:.1f}ms")
    print(f"Max Input Tokens: {summary['max_input_tokens']}")
    print(f"Total Input Tokens: {summary['total_input_tokens']}")
    print(f"Cache Hit Ratio: {summary['cache_hit_ratio']:.1%}")
    print("=" * 60)
