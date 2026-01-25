# Manus Replication

Implementation of Manus-style context engineering experiments for AI agents, based on [Context Engineering for AI Agents: Lessons from Building Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus).

## Overview

This project experiments with techniques to optimize agent context management through:

- **Stable Prefixes** - Enable KV-cache reuse with frozen system prompts
- **Filesystem Memory** - Offload large outputs to files, reference by path
- **Token Growth Control** - Measure and minimize context expansion across steps
- **Error Evidence** - Preserve error outputs for recovery analysis

## Quick Start

```bash
# Install dependencies (from repo root)
uv sync

# Run experiment
cd maning_context
uv run python run_experiment.py

# Results will be in workspace/
# - metrics/run_steps.csv - Per-step metrics
# - metrics/run_summary.json - Aggregate results
# - trace.jsonl - Full action/observation log
```

## Configuration

Edit `config.yaml` to customize:

```yaml
agent:
  model: "gpt-4o"
  max_steps: 50

workspace:
  root: "./workspace"
  data_file: "data/raw.csv"

task:
  description: "Clean the dataset and validate quality"
```

## Architecture

### Core Components

**agent_loop.py** - Main execution loop
- Implements stable prefix pattern
- Reconstructs state from filesystem each step
- Enforces one decision iteration per turn

**constitution.py** - System prompts and rules
- Defines agent capabilities and constraints
- Specifies tool usage patterns
- Sets error handling protocols

**tools.py** - Filesystem operations
- `fs_read(path)` - Read file contents
- `fs_write(path, content)` - Write file
- `fs_list(dir)` - List directory contents
- `fs_append(path, content)` - Append to file

**metrics.py** - Performance tracking
- TTFT (Time To First Token)
- End-to-end latency
- Cached vs prompt tokens
- Per-step metrics

**openai_wrapper.py** - OpenAI API client
- Implements prompt caching with `prompt_cache_key`
- Token usage tracking
- Error handling and retries

### Workspace Layout

```
workspace/
├── data/
│   └── raw.csv           # Input data
├── scripts/
│   ├── clean.py          # Generated cleaning script
│   └── validate.py       # Generated validation script
├── reports/
│   └── quality.json      # Validation results
├── artifacts/            # Offloaded outputs
│   ├── errors/           # Error evidence
│   └── previews/         # Large output previews
├── metrics/
│   ├── run_steps.csv     # Per-step metrics
│   └── run_summary.json  # Aggregate statistics
├── todo.md               # Remaining goals (rewritten)
├── index.md              # File registry
├── progress.md           # Append-only achievements
└── trace.jsonl           # Action/observation log
```

## Agent Protocol

### Prompt Construction

Each step prompt = Frozen PREFIX + STATE snapshot + last event excerpt + todo recitation

**Frozen PREFIX** (stable for KV-cache):
- System prompt
- Tool definitions
- Agent rules

**STATE snapshot** (reconstructed from filesystem):
- File registry (index.md)
- Recent progress (progress.md)
- Last N events from trace.jsonl

**Recitation** (todo.md at prompt end):
- Only remaining goals
- Not completed tasks

### Memory Strategy

- **Large outputs** → `artifacts/previews/` (referenced by path)
- **Errors** → `artifacts/errors/` (preserved for recovery)
- **State** → Reconstructed from filesystem each step
- **Progress** → Append-only `progress.md`

### Error Handling

- Full error output saved to `artifacts/errors/`
- Error path referenced in next prompt (not hidden)
- Agent must read error file to diagnose
- Enables learning from failures

## LLM Backends

The experiment framework supports two LLM backends for comparing cached vs uncached inference:

### OpenAI (Default)
Cloud-based inference with prompt caching support.

**Features:**
- Prompt caching with KV-cache reuse
- Token usage tracking (including cached tokens)
- Cost estimation
- Models: gpt-4o-mini, gpt-4o

**Usage:**
```bash
python run_experiment.py --backend openai --config config.yaml
```

**Config:**
```yaml
model:
  name: "gpt-4o-mini"
  backend: "openai"
  tier: "flex"  # or "standard", "batch"
```

### vLLM (Local)
Local inference using vLLM server with OpenAI-compatible API.

**Features:**
- No prompt caching (cached_tokens always 0)
- Zero direct cost (local compute)
- Enables comparison: cached (OpenAI) vs uncached (vLLM)
- Models: Any local model (Llama, Qwen, etc.)

**Usage:**
```bash
# Start vLLM server first
python -m vllm.entrypoints.openai.api_server --model meta-llama/Llama-3.1-8B-Instruct

# Run experiment
python run_experiment.py --backend vllm --vllm-url http://localhost:8000/v1
```

**Config:**
```yaml
model:
  name: "meta-llama/Llama-3.1-8B-Instruct"
  backend: "vllm"

vllm:
  base_url: "http://localhost:8000/v1"
```

**Metrics Comparison:**
| Metric | OpenAI | vLLM |
|--------|--------|------|
| cached_tokens | >0 | 0 |
| estimated_cost_usd | >0 | 0 |
| ttft_ms | Varies | Varies |

This enables direct comparison of:
- Cache hit rates
- Performance with/without caching
- Cost implications

## Experiment Variants

The codebase supports testing different configurations:

### Baseline (A1)
- Stable prefix + filesystem memory + recitation
- Prompt caching enabled
- Error evidence retained

### Cache Collapse (B1)
- Changing token in prefix each step
- Measures KV-cache effectiveness

### Token Growth (C1)
- No output offloading to files
- Measures context expansion rate

### Attention Steering (E2)
- No todo recitation at prompt end
- Tests goal retention without reminder

### Error Evidence (F1/F2)
- F1: Keep error evidence in artifacts
- F2: Hide errors from agent
- Compares recovery rates

### Tool Space (D1/D2)
- D1: Stable tool definitions
- D2: Dynamic tools per step
- Tests tool-space stability impact

## Metrics

### Tracked Per Step

- **step** - Step number
- **ttft_ms** - Time to first token (cache effectiveness)
- **latency_ms** - End-to-end latency
- **prompt_tokens** - Total prompt tokens
- **cached_tokens** - Tokens served from cache
- **completion_tokens** - Generated tokens
- **total_tokens** - Prompt + completion
- **cache_hit_rate** - cached_tokens / prompt_tokens

### Summary Metrics

- Total steps
- Total tokens
- Average TTFT
- Average cache hit rate
- Token growth rate (tokens per step)

## Key Principles

### Stable Prefix Pattern
- Freeze system prompt and tool definitions
- No timestamps, UUIDs, or changing values in prefix
- Use consistent `prompt_cache_key` across steps
- Ensure prefix >= 1024 tokens for cache activation

### Filesystem Memory
- Offload large outputs to files
- Reference by path only in prompts
- Reconstruct state from files each step
- Never include full file contents in prompt unless needed

### Error Transparency
- Never hide errors from agent
- Preserve full error output in artifacts
- Reference error file path in prompt
- Let agent diagnose and recover

### Token Discipline
- Monitor `cached_tokens` vs `prompt_tokens`
- Watch token growth across steps
- Use deterministic templates for state
- Avoid history leakage into prompts

## Requirements

- Python 3.12+
- OpenAI API key with prompt caching support
- UV package manager

## Running Experiments

```bash
# Basic run
uv run python run_experiment.py

# Check results
cat workspace/metrics/run_summary.json

# View trace
cat workspace/trace.jsonl | jq

# Analyze token usage
cat workspace/metrics/run_steps.csv | column -t -s,
```

## Interpreting Results

### High Cache Hit Rate (>80%)
- Stable prefix working well
- KV-cache effectively reusing computation
- Lower latency and cost

### Low Cache Hit Rate (<50%)
- Prefix instability detected
- Check for changing values in system prompt
- Verify `prompt_cache_key` consistency

### Token Growth >100/step
- Context expanding too fast
- History leaking into prompts
- Check state reconstruction logic

### Frequent Errors
- Review `workspace/artifacts/errors/`
- Check tool error messages
- Validate tool implementations

## References

- [Manus Blog Post](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [OpenAI Prompt Caching](https://platform.openai.com/docs/api-reference/prompt-caching)
- [Anthropic Context Engineering](https://www.anthropic.com/engineering/context-engineering-for-ai-agents)

## License

MIT
