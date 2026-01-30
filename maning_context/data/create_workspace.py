"""Create workspace directory structure for Manus replication."""
import os
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent / "workspace"


def create_workspace():
    for dir_path in [
        WORKSPACE / "data",
        WORKSPACE / "reports",
        WORKSPACE / "scripts",
        WORKSPACE / "artifacts" / "errors",
        WORKSPACE / "artifacts" / "logs",
        WORKSPACE / "artifacts" / "previews",
        WORKSPACE / "metrics",
    ]:
        dir_path.mkdir(parents=True, exist_ok=True)

    todo_path = WORKSPACE / "todo.md"
    if not todo_path.exists():
        todo_path.write_text(
            "# Remaining Goals\n\n"
            "- Clean data/raw.csv according to spec\n"
            "- Validate output with scripts/validate.py\n"
            "- Generate reports/quality.json\n"
        )

    index_path = WORKSPACE / "index.md"
    if not index_path.exists():
        index_path.write_text(
            "# File Registry\n\n"
            "## Data\n"
            "- data/raw.csv - Input data with missing values and outliers\n"
            "- data/clean.csv - Cleaned output (to be generated)\n\n"
            "## Scripts\n"
            "- scripts/clean.py - Cleaning script (to be created)\n"
            "- scripts/validate.py - Validation script (to be created)\n\n"
            "## Reports\n"
            "- reports/quality.json - Validation output (to be generated)\n\n"
            "## Other\n"
            "- todo.md - Current task list\n"
            "- index.md - This file\n"
            "- trace.jsonl - Event log\n"
        )

    steps_csv = WORKSPACE / "metrics" / "run_steps.csv"
    if not steps_csv.exists():
        steps_csv.write_text(
            "variant_id,task_id,step_idx,ttft_ms,e2e_ms,input_tokens,output_tokens,cached_tokens,uncached_tokens,estimated_cost_usd,tool_name,tool_success,prompt_cache_key\n"
        )

    trace_path = WORKSPACE / "trace.jsonl"
    if not trace_path.exists():
        trace_path.write_text("")

    artifact_index = WORKSPACE / "artifacts" / "index.md"
    if not artifact_index.exists():
        artifact_index.write_text("# Artifact Registry\n\n")

    print(f"Workspace created at {WORKSPACE}")


if __name__ == "__main__":
    create_workspace()
