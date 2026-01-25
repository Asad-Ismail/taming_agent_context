"""File system and shell tools for Manus replication agent."""
import os
import subprocess
import fnmatch
from pathlib import Path
from typing import Callable

WORKSPACE = Path(__file__).parent / "workspace"
ALLOWED_SCRIPTS = {"clean.py", "validate.py"}


def _ensure_in_workspace(path: str) -> Path:
    resolved = (WORKSPACE / path).resolve()
    if not str(resolved).startswith(str(WORKSPACE.resolve())):
        raise ValueError(f"Path outside workspace: {path}")
    return resolved.relative_to(WORKSPACE)


def fs_read(path: str) -> str:
    full_path = WORKSPACE / _ensure_in_workspace(path)
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return full_path.read_text()


def fs_write(path: str, content: str) -> str:
    full_path = WORKSPACE / _ensure_in_workspace(path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    return f"Wrote {len(content)} characters to {path}"


def fs_list(dir: str) -> list[str]:
    full_dir = WORKSPACE / _ensure_in_workspace(dir)
    if not full_dir.exists() or not full_dir.is_dir():
        raise NotADirectoryError(f"Not a directory: {dir}")
    return [f.name for f in full_dir.iterdir()]


def fs_grep(pattern: str, glob: str) -> list[str]:
    matches = []
    for root, dirs, files in os.walk(WORKSPACE):
        for filename in fnmatch.filter(files, glob):
            filepath = Path(root) / filename
            try:
                content = filepath.read_text()
                for i, line in enumerate(content.split("\n"), 1):
                    if pattern in line:
                        rel_path = filepath.relative_to(WORKSPACE)
                        matches.append(f"{rel_path}:{i}:{line.strip()}")
            except Exception:
                pass
    return matches[:100]


def shell_run(cmd: str) -> dict:
    cmd = cmd.strip()
    if not cmd.startswith("python "):
        raise ValueError("Only python commands are allowed")

    script_path = cmd.split(maxsplit=1)[1]
    if not script_path.startswith("scripts/"):
        raise ValueError("Script must be in scripts/ directory")

    script_name = Path(script_path).name
    if script_name not in ALLOWED_SCRIPTS:
        raise ValueError(f"Script not allowed: {script_name}")

    full_script = WORKSPACE / script_path
    if not full_script.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    try:
        result = subprocess.run(
            ["python", str(full_script)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(WORKSPACE)
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Script timed out: {script_path}")
    except Exception as e:
        raise RuntimeError(f"Script execution failed: {e}")


def task_complete() -> str:
    return "Task marked as complete. The agent will stop after this step."


TOOL_FUNCTIONS: dict[str, Callable] = {
    "fs_read": fs_read,
    "fs_write": fs_write,
    "fs_list": fs_list,
    "fs_grep": fs_grep,
    "shell_run": shell_run,
    "task_complete": task_complete,
}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "fs_read",
            "description": "Read the contents of a file from the workspace",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace directory (e.g., 'data/raw.csv', 'todo.md')"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fs_write",
            "description": "Write content to a file in the workspace",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace (e.g., 'scripts/clean.py', 'data/clean.csv')"},
                    "content": {"type": "string", "description": "Content to write to the file"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fs_list",
            "description": "List files and directories in a workspace directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir": {"type": "string", "description": "Directory path relative to workspace (e.g., 'data', 'scripts', '.')"}
                },
                "required": ["dir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fs_grep",
            "description": "Search for a text pattern in files matching a glob pattern",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Text pattern to search for in files"},
                    "glob": {"type": "string", "description": "File glob pattern to match files (e.g., '*.py', '*.md', 'data/*.csv')"}
                },
                "required": ["pattern", "glob"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shell_run",
            "description": "Execute a Python script in the workspace scripts directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string", "description": "Python command to run scripts (e.g., 'python scripts/clean.py', 'python scripts/validate.py')"}
                },
                "required": ["cmd"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "Call this tool when you have completed the task successfully. After running validation and confirming data/clean.csv exists and reports/quality.json shows pass=true, call this to signal completion.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]
