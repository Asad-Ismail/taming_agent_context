"""Main agent loop for Manus replication."""
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Literal

from openai_wrapper import OpenAIStreamWrapper, StepMetrics
from constitution import get_prefix, get_prompt_cache_key, TODO_TEMPLATE, INDEX_TEMPLATE
from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS

WORKSPACE = Path(__file__).parent / "workspace"


class AgentLoop:
    def __init__(self, variant: str = "A1", max_steps: int = 20,
                 wrapper: OpenAIStreamWrapper | None = None,
                 large_output_threshold: int = 150):
        self.variant = variant
        self.max_steps = max_steps
        self.wrapper = wrapper or OpenAIStreamWrapper()
        self.metrics: list[StepMetrics] = []
        self.trace: list[dict] = []
        self.large_output_threshold = large_output_threshold

    def _build_messages(self, state_snapshot: str) -> list[dict]:
        prefix = get_prefix(self.variant)

        todo_content = (WORKSPACE / "todo.md").read_text()

        messages = [
            {"role": "system", "content": prefix},
            {"role": "user", "content": f"{state_snapshot}\n\nCurrent todo.md:\n{todo_content}"}
        ]
        return messages

    def _build_messages_with_fresh_uuid(self, state_snapshot: str, step: int = 0) -> list[dict]:
        if self.variant == "B1":
            import uuid
            run_uuid = str(uuid.uuid4())
            prefix = f"RunID: {run_uuid}\n\n" + get_prefix("A1")
            print(f"[B1 DEBUG] Step {step}: System prefix starts with RunID: {run_uuid[:8]}...")
            print(f"[B1 DEBUG] Full prefix length: {len(prefix)} chars")
        else:
            prefix = get_prefix(self.variant)

        todo_content = (WORKSPACE / "todo.md").read_text()

        messages = [
            {"role": "system", "content": prefix},
            {"role": "user", "content": f"{state_snapshot}\n\nCurrent todo.md:\n{todo_content}"}
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
        # fs_read and fs_write: never offload (can be re-run, confirmations are small)
        if tool_name in ["fs_read", "fs_write"]:
            return content

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

    async def run(self) -> dict:
        state_snapshot = self._build_state_snapshot()
        build_msg = self._build_messages_with_fresh_uuid if self.variant == "B1" else self._build_messages
        messages = build_msg(state_snapshot, step=0)

        for step in range(self.max_steps):
            prompt_cache_key = get_prompt_cache_key(self.variant)

            msg, metrics = await self.wrapper.call(
                messages=messages,
                tools=TOOL_SCHEMAS,
                prompt_cache_key=prompt_cache_key,
                variant_id=self.variant,
                task_id="data_cleaning",
                step_idx=step,
            )

            self.metrics.append(metrics)
            self._update_trace(step, "model_call", {
                "ttft_ms": metrics.ttft_ms,
                "input_tokens": metrics.input_tokens,
                "output_tokens": metrics.output_tokens,
                "cached_tokens": metrics.cached_tokens,
            })

            content = msg.content or ""
            task_signaled_complete = False

            if msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    result, success = self._execute_tool(tool_name, arguments)
                    result = self._offload_large_output(result, tool_name)

                    if tool_name == "task_complete":
                        task_signaled_complete = True
                        print(f"[COMPLETE] Agent signaled task completion at step {step + 1}")
                        self._update_trace(step, "task_complete_signaled", {
                            "success": True,
                            "method": "tool_call"
                        })

                    metrics.tool_name = tool_name
                    metrics.tool_success = success

                    self._update_trace(step, "tool_call", {
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "success": success,
                        "result_preview": result[:200],
                    })

                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tool_call.model_dump()]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })

            else:
                messages.append({"role": "assistant", "content": content})

            if task_signaled_complete:
                print(f"[SUCCESS] Agent terminated at step {step + 1} (task_complete called)")
                break

            if self._check_success():
                print(f"[SUCCESS] Task validated at step {step + 1} (quality.json passed)")
                self._update_trace(step, "task_complete", {"success": True})
                break

            state_snapshot = self._build_state_snapshot(content)
            messages = build_msg(state_snapshot, step=step+1)
            messages.append({"role": "assistant", "content": f"Previous response: {content}"})

        total_cost = sum(m.estimated_cost_usd for m in self.metrics)
        avg_ttft = sum(m.ttft_ms for m in self.metrics[1:]) / max(1, len(self.metrics) - 1)
        cache_hit_ratio = sum(m.cached_tokens for m in self.metrics) / max(1, sum(m.input_tokens for m in self.metrics))

        return {
            "variant": self.variant,
            "total_steps": len(self.metrics),
            "success": self._check_success(),
            "total_cost_usd": round(total_cost, 4),
            "avg_ttft_ms": round(avg_ttft, 2),
            "max_input_tokens": max(m.input_tokens for m in self.metrics),
            "total_input_tokens": sum(m.input_tokens for m in self.metrics),
            "cache_hit_ratio": round(cache_hit_ratio, 3),
        }


async def run_agent_variant(variant: str = "A1", max_steps: int = 20, wrapper: OpenAIStreamWrapper | None = None) -> dict:
    agent = AgentLoop(variant=variant, max_steps=max_steps, wrapper=wrapper)
    return await agent.run()
