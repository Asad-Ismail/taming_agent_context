# Taming Agent Context

Practical experiments on managing LLM agent context: how to keep costs down, cache hits high, and token budgets under control.

## What's Here

### 1. MCP Tool Scaling (`taming_mcps/`)

Problem: Loading 500+ MCP tools into context burns tokens and hits limits.

Solution: File Tree pattern from [Anthropic's MCP post](https://www.anthropic.com/engineering/code-execution-with-mcp). One `run_python` tool discovers and calls others via filesystem navigation.

Result: ~50% token reduction, no tool count limit.

```bash
cd taming_mcps
uv run python build_registry.py    # generates ./servers/ with tool wrappers
uv run python code_mode.py         # file tree approach
uv run python traditional_mode.py  # baseline: all tools in context
uv run python compare_token_usage.py
```

### 2. Context Engineering (`maning_context/`)

Experiments based on [Manus context engineering](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus). Data cleaning pipeline as test task.

Tests variants:
- Stable prefix vs dynamic prefix (cache collapse)
- Filesystem memory vs in-context history (token growth)
- Error evidence retention vs hiding (recovery behavior)
- Tool schema stability (cache preservation)

```bash
cd maning_context
uv run python run_experiment.py
```

### 3. Prompt Cache Testing (`maning_context/`)

Validates cache behavior from [this post](https://asad-ismail.github.io/posts/prompt_caching/). Tests UUID placement, tool ordering, temperature independence.

```bash
cd maning_context
uv run python test_prompt_cache.py                    # all suites
uv run python test_prompt_cache.py --suite baseline   # specific suite
```

Test suites:
- `baseline`: identical prompts should cache
- `uuid_system_start`: breaks cache (early divergence)
- `uuid_system_end`: breaks cache when tools present
- `uuid_user_message`: preserves cache (late binding)
- `tool_prepend`: breaks more cache than append
- `tool_append`: breaks less cache
- `temperature_variation`: no cache impact
- `user_message_rotation`: preserves cache

## Setup

```bash
uv sync
cp .env.example .env
# add OPENAI_API_KEY to .env
```

Requirements:
- Python 3.12+
- uv
- OpenAI API key
- MCP servers in PATH (for taming_mcps)

## Structure

```
taming_mcps/
  build_registry.py      # generate tool wrappers
  code_mode.py           # file tree pattern
  traditional_mode.py    # all tools in context
  mcp_bridge.py          # runtime MCP connection

maning_context/
  agent_loop.py          # main agent loop
  run_experiment.py      # experiment runner
  test_prompt_cache.py   # cache testing
  prompt_cache_config.yaml
  tools.py               # tool definitions
  workspace/             # agent sandbox
```

## References

- [Anthropic: Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [Manus: Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Why Your Prompt Cache Keeps Missing](https://asad-ismail.github.io/posts/prompt_caching/)
