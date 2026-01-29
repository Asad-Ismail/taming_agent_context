# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Critical Requirements

1. **Always use `uv` as package manager** - never use pip, conda, or poetry
2. **Always run scripts with `uv run`** - e.g., `uv run python script.py`
3. **Create `.env` if not present** - copy from `.env.example` and fill in values
4. **Load environment with `python-dotenv`** - all scripts must load `.env` at startup

## Project Overview

This repository contains two distinct research projects exploring agent context management and tool access patterns:

### 1. MCP Context Comparison (`taming_mcps/`)
Demonstrates two approaches to using MCP (Model Context Protocol) tools: Traditional Mode (all tools in context) vs Code Mode (tool discovery via Python execution). This implements the "File Tree" discovery pattern from [Anthropic's Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp).

**Key Finding:** Code Mode reduces token usage by ~50% and scales to unlimited tools by keeping only a `run_python` tool in context, while Traditional Mode hits hard capacity limits with 500+ tools.

### 2. Manus Replication (`maning_context/`)
Implementation of Manus-style context engineering experiments for AI agents, based on the [Manus blog post](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus). Focuses on a data cleaning pipeline task to measure:

- KV-cache effectiveness via stable prefixes
- Token growth patterns with different memory strategies
- Impact of recitation, error evidence retention, and tool-space stability

## Common Commands

### MCP Context Comparison

```bash
# Build the tool registry (generates ./servers/ directory structure)
cd taming_mcps
uv run python build_registry.py

# Run individual modes
uv run python traditional_mode.py    # All tools in LLM context
uv run python code_mode.py           # Tool discovery via Python execution

# Run comparison (executes both and reports metrics)
uv run python compare_token_usage.py
```

### Check OpenAI Connection

```bash
# Test API connectivity
uv run python check_connection.py
```

## Architecture

### MCP Comparison Architecture

**Traditional Mode:**
- All MCP tools loaded directly into LLM context as function definitions
- Server configs in `start_mcp_servers()` define which MCP servers to connect
- Tools converted to OpenAI function format with `server_name_tool_name` prefix

**Code Mode:**
- Single `run_python` tool in context
- `build_registry.py` generates Python wrappers in `./servers/` directory tree
- `mcp_bridge.py` provides runtime connection between generated code and active MCP sessions
- LLM discovers tools by exploring `./servers/` (File Tree pattern)

**The Bridge Pattern:**
The `mcp_bridge.py` module is critical - it's injected into the code execution environment and provides the `call_mcp_tool()` function that connects generated wrapper code to active MCP sessions stored in `ACTIVE_SESSIONS`.

**Server Configuration:**
Both modes use the same server configs in `server_configs` lists. When adding new MCP servers for comparison, update both:
- `build_registry.py` line 84-90
- `traditional_mode.py` line 21-27
- `code_mode.py` line 64-67

### Manus Replication Architecture

**Workspace Layout:**
```
/workspace/
  data/raw.csv           # Input data
  data/clean.csv         # Agent output
  reports/quality.json   # Validation output
  scripts/clean.py       # Generated/edited
  scripts/validate.py    # Generated/edited
  todo.md                # Rewritten each step
  index.md               # File registry
  progress.md            # Append-only achievements
  trace.jsonl            # Action/observation log
  artifacts/             # errors/logs/previews
  metrics/               # run_steps.csv, run_summary.json
```

**Agent Loop Protocol:**
- One decision iteration per step
- Prompt = Frozen PREFIX + STATE snapshot + last event excerpt
- Large outputs offloaded to artifacts (referenced by path only)
- todo.md recited at end of prompt (remaining goals only)
- Errors preserved in artifacts/errors/ + referenced in state

**Variants to Test:**
- A1: Stable prefix + filesystem memory + recitation (baseline)
- B1: Changing token in prefix (cache collapse test)
- C1: No offloading (token growth test)
- E2: No recitation (attention steering test)
- F1/F2: Keep/hide error evidence (recovery test)
- D1/D2: Stable/dynamic tools (tool-space test)

## Environment Setup

### Required Environment Variables

The project requires these variables in `.env`:

```bash
OPENAI_API_KEY=<your-key>
OPENAI_API_BASE=<your-endpoint>  # Optional, for custom deployments
LANGFUSE_SECRET_KEY=<optional>    # For observability
LANGFUSE_PUBLIC_KEY=<optional>
LANGFUSE_BASE_URL=<optional>
SSL_CERT_FILE=<optional>          # For corporate proxies
REQUESTS_CA_BUNDLE=<optional>
```

### Dependencies

**Package Management:**
- Always use `uv` as package manager
- Always use `uv sync` to install dependencies
- Package versions are pinned in `uv.lock` for reproducibility
- To add new packages: `uv add <package-name>`
- To add dev packages: `uv add --dev <package-name>`
- To run Python scripts with pinned versions: `uv run <script>`

**Initial setup:**
```bash
uv sync
```

**Adding dependencies:**
```bash
uv add openai
uv add --dev pytest
```

**Running scripts:**
```bash
uv run python build_registry.py
uv run python traditional_mode.py
```

Key dependencies (pinned in uv.lock):
- `openai` - OpenAI API client
- `mcp` - Model Context Protocol SDK
- `python-dotenv` - Environment management

## Testing

Both projects include token usage tracking. When running experiments:

- MCP comparison reports: Input/Output tokens per turn, total tokens, tools in context
- Manus replication logs: TTFT, e2e latency, cached tokens, per-step metrics to `metrics/run_steps.csv`

## Important Notes

- The MCP servers used (`uvx mcp-server-*`, `npx @modelcontextprotocol/server-*`) must be installed and available in PATH
- The `build_registry.py` script must be run before `code_mode.py` to generate the `./servers/` directory
- For Manus experiments, ensure OpenAI prompt caching requirements are met (prefix >= 1024 tokens, use `prompt_cache_key` consistently)

## Coding Standards

### Code Style

**No verbose explanations in code:**
- Code should be self-documenting through clear naming and structure
- Keep functions small and focused (single responsibility)
- No paragraph-length comments explaining "what" or "why next steps"
- Put detailed explanations in README.md, not in code comments

**Clean and concise:**
- Prefer Python built-ins and standard library over custom implementations
- Use type hints for function signatures
- Avoid redundant comments that restate obvious code
- No emojis in code or comments
- Always use `uv` for package management and `uv run <script>` to execute scripts

**Example - Don't:**
```python
# Step 1: Load the data from CSV file into memory for processing
# This is important because we need to analyze the user patterns later
def load_data(file_path):
    """Load data from CSV file and return as list of dicts."""
    data = []
    with open(file_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data
```

**Example - Do:**
```python
def load_data(path: str) -> list[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))
```

### Context Engineering Best Practices

**Stable Prefix Pattern:**
- Freeze system prompt and tool definitions
- No timestamps, UUIDs, or changing values in prefix
- Use `prompt_cache_key` consistently across steps
- Ensure prefix >= 1024 tokens for cache activation

**Filesystem Memory:**
- Offload large outputs to files, reference by path in prompt
- Maintain `index.md` as file registry
- Use `todo.md` for recitation (remaining goals only)
- Keep `progress.md` as append-only achievement log

**Error Handling:**
- Preserve full error outputs in `artifacts/errors/`
- Reference error files in prompts (don't hide failures)
- Log all actions to `trace.jsonl` including wrong turns

**Token Management:**
- Monitor `cached_tokens` vs `prompt_tokens` per step
- Track TTFT (time to first token) for cache effectiveness
- Watch for token growth across steps (indicates history leakage)
- Use deterministic templates for state reconstruction
