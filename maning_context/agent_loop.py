"""Main agent loop for Manus replication."""
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Literal

from openai_wrapper import OpenAIStreamWrapper, StepMetrics
from constitution import get_prefix, get_prompt_cache_key
from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS

WORKSPACE = Path(__file__).parent / "workspace"


class AgentLoop:
    def __init__(self, variant: str = "A1", max_steps: int = 20,
                 wrapper: OpenAIStreamWrapper | None = None,
                 large_output_threshold: int = 150,
                 disable_offload: bool = False):
        self.variant = variant
        self.max_steps = max_steps
        self.wrapper = wrapper or OpenAIStreamWrapper()
        self.metrics: list[StepMetrics] = []
        self.trace: list[dict] = []
        self.large_output_threshold = large_output_threshold
        self.disable_offload = disable_offload  # C1 variant: no offloading

    def _build_messages(self, state_snapshot: str) -> list[dict]:
        prefix = get_prefix(self.variant)

        # Agent-driven recitation: the system prompt instructs the agent to
        # read and update todo.md itself. We don't inject it mechanically.
        # This tests whether the agent follows recitation discipline.
        messages = [
            {"role": "system", "content": prefix},
            {"role": "user", "content": state_snapshot}
        ]
        return messages

    def _build_state_snapshot(self, last_event: str = "") -> str:
        index_content = (WORKSPACE / "index.md").read_text()

        recent_errors = []
        error_files = list((WORKSPACE / "artifacts" / "errors").glob("*.txt"))[-3:]
        for ef in error_files:
            recent_errors.append(f"See: artifacts/errors/{ef.name}")

        state_parts = ["## Workspace State", "", index_content]
        if recent_errors:
            state_parts.extend(["## Recent Errors", "\n".join(recent_errors), ""])

        artifact_index = WORKSPACE / "artifacts" / "index.md"
        if artifact_index.exists() and artifact_index.stat().st_size > 32:
            state_parts.extend(["## Available Artifacts", artifact_index.read_text(), ""])

        if last_event:
            state_parts.extend(["## Last Event", last_event, ""])
        return "\n".join(state_parts)

    def _execute_tool(self, tool_name: str, arguments: dict) -> tuple[str, bool]:
        try:
            func = TOOL_FUNCTIONS[tool_name]
            result = func(**arguments)
            return str(result), True
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"

            error_file = WORKSPACE / "artifacts" / "errors" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{tool_name}_error.txt"
            error_file.write_text(error_msg)

            return f"Error saved to artifacts/errors/{error_file.name}", False

    def _offload_large_output(self, content: str, tool_name: str) -> str:
        # C1 variant: disable all offloading to test token growth
        # This will cause context explosion and likely hit rate limits
        # That failure IS the point - demonstrates need for filesystem memory
        if self.disable_offload:
            return content

        # fs_write: confirmations are small, never offload
        if tool_name == "fs_write":
            return content

        # fs_read: offload large files to prevent context explosion
        # Keep small files inline for agent to reason about
        if tool_name == "fs_read" and len(content) > self.large_output_threshold:
            artifact_file = WORKSPACE / "artifacts" / "previews" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_fs_read_output.txt"
            artifact_file.write_text(content)
            self._add_to_registry(artifact_file, tool_name, content)
            # Provide head preview so agent knows the structure
            lines = content.split('\n')
            preview = '\n'.join(lines[:10])
            return f"[File too large ({len(lines)} lines). First 10 lines:]\n{preview}\n\n[Full content saved to: artifacts/previews/{artifact_file.name}]"

        # shell_run: always offload to logs/ (execution output, not preview)
        if tool_name == "shell_run":
            log_file = WORKSPACE / "artifacts" / "logs" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_shell_output.txt"
            log_file.write_text(content)
            self._add_to_registry(log_file, tool_name, content)

            # Generate smart summary
            summary = self._summarize_shell_result(content)
            return f"{summary}\n[Full output: artifacts/logs/{log_file.name}]"

        # fs_list: offload only if large (current behavior)
        if len(content) > self.large_output_threshold:
            artifact_file = WORKSPACE / "artifacts" / "previews" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{tool_name}_output.txt"
            artifact_file.write_text(content)
            self._add_to_registry(artifact_file, tool_name, content)
            return f"[See: artifacts/{artifact_file.name}]"

        return content

    def _summarize_shell_result(self, content: str) -> str:
        """Generate a human-readable summary of shell execution result."""
        try:
            data = eval(content)
            returncode = data.get("returncode", -1)
            stdout = data.get("stdout", "").strip()
            stderr = data.get("stderr", "").strip()

            # Success case
            if returncode == 0:
                status = "✅ Execution successful"
                parts = [f"{status} (return code: {returncode})"]
                if stdout:
                    preview = stdout.split('\n')[0][:100]
                    parts.append(f'stdout: "{preview}"')
                return "\n".join(parts)

            # Failure case
            else:
                status = "❌ Execution failed"
                parts = [f"{status} (return code: {returncode})"]
                if stderr:
                    # Show first line of error
                    error_line = stderr.split('\n')[0][:150]
                    parts.append(f'stderr: "{error_line}"')
                elif stdout:
                    preview = stdout.split('\n')[0][:100]
                    parts.append(f'stdout: "{preview}"')
                return "\n".join(parts)

        except Exception:
            # Fallback for non-JSON output
            preview = content[:150].replace('\n', ' ')
            return f'Execution output: "{preview}..."'

    def _update_trace(self, step: int, event_type: str, data: dict):
        trace_entry = {
            **data,
            "step": step,
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
        }
        self.trace.append(trace_entry)

        with open(WORKSPACE / "trace.jsonl", "a") as f:
            f.write(f"{json.dumps(trace_entry)}\n")

    def _get_artifact_structure(self, content: str, tool_name: str) -> dict:
        if tool_name == "shell_run":
            try:
                data = eval(content)
                return {
                    "type": "shell_run (execution output)",
                    "schema": list(data.keys()),
                    "preview": content[:100]
                }
            except:
                return {"type": "shell_run (execution output)", "preview": content[:100]}
        elif tool_name == "fs_read":
            lines = content.split('\n')
            return {
                "type": "fs_read (file content)",
                "schema": f"{len(lines)} lines",
                "preview": '\n'.join(lines[:3])
            }
        elif tool_name == "fs_write":
            return {"type": "fs_write (confirmation)", "preview": content[:100]}
        elif tool_name == "fs_list":
            return {"type": "fs_list (array)", "schema": "file names", "preview": content[:100]}
        return {"preview": content[:100]}

    def _add_to_registry(self, artifact_path: Path, tool_name: str, content: str):
        registry = WORKSPACE / "artifacts" / "index.md"
        info = self._get_artifact_structure(content, tool_name)

        size = len(content)
        size_str = f"{size} bytes" if size < 1024 else f"{size/1024:.1f}KB"
        preview = info["preview"][:150].replace('\n', '\\n')

        relative_path = artifact_path.relative_to(WORKSPACE)
        entry = f"""## [{artifact_path.name}]({relative_path})
**Type**: {info.get('type', tool_name)}
**Size**: {size_str}
**Created**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Preview**: {preview}...

---
"""
        with open(registry, 'a') as f:
            f.write(entry)

    def _check_success(self) -> bool:
        clean_csv = WORKSPACE / "data" / "clean.csv"
        quality_json = WORKSPACE / "reports" / "quality.json"

        if not clean_csv.exists() or not quality_json.exists():
            return False

        try:
            quality = json.loads(quality_json.read_text())
            return quality.get("pass", False)
        except Exception:
            return False
