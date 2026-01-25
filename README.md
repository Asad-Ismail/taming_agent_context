# Taming Agent Context

Research implementations exploring agent context management and tool access patterns for large language models.

## Overview

This repository contains two distinct research projects:

1. **MCP Context Comparison** (`taming_mcps/`) - Demonstrates token-efficient MCP tool usage
2. **Manus Replication** (`maning_context/`) - Implements Manus-style context engineering experiments

## Projects

### MCP Context Comparison

Compares two approaches to using MCP (Model Context Protocol) tools:

**Traditional Mode:** All tools loaded into LLM context as function definitions
- Hits capacity limits with 500+ tools
- High token usage per request

**Code Mode:** Tool discovery via Python execution (File Tree pattern)
- Single `run_python` tool in context
- ~50% token reduction
- Scales to unlimited tools

Based on [Anthropic's Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)

### Manus Replication

Imperiments with context engineering techniques from [Manus blog post](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus):

- KV-cache effectiveness via stable prefixes
- Token growth patterns with memory strategies
- Impact of recitation and error evidence retention

## Quick Start

```bash
# Install dependencies
uv sync

# MCP Context Comparison
cd taming_mcps
uv run python build_registry.py    # Generate tool registry
uv run python code_mode.py         # Run code mode
uv run python traditional_mode.py  # Run traditional mode

# Manus Replication
cd maning_context
uv run python run_experiment.py    # Run agent experiment
```

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- OpenAI API key
- MCP servers available in PATH (`uvx mcp-server-*`, `npx @modelcontextprotocol/server-*`)

## Environment Setup

Create `.env` file:

```bash
OPENAI_API_KEY=<your-key>
OPENAI_API_BASE=<your-endpoint>  # Optional
```

## Project Structure

```
taming_agent_context/
├── taming_mcps/              # MCP tool comparison
│   ├── build_registry.py     # Generate Python wrappers
│   ├── code_mode.py          # File Tree pattern
│   └── traditional_mode.py   # All tools in context
├── maning_context/           # Manus replication
│   ├── agent_loop.py         # Main execution loop
│   ├── constitution.py       # System prompts
│   ├── metrics.py            # Token tracking
│   └── run_experiment.py     # Experiment runner
├── CLAUDE.md                 # Claude Code instructions
└── README.md                 # This file
```

## Key Findings

### MCP Context Comparison

| Mode | Tools in Context | Avg Tokens/Request | Scalability |
|------|-----------------|-------------------|-------------|
| Traditional | 500+ | High | Limited (tool count) |
| Code | 1 | ~50% reduction | Unlimited |

### Manus Replication

- Stable prefixes enable effective KV-cache reuse
- Filesystem memory reduces token growth
- Error evidence retention improves recovery

## Documentation

- [CLAUDE.md](./CLAUDE.md) - Detailed project documentation and coding standards
- [maning_context/README.md](./maning_context/README.md) - Manus experiment details

## License

MIT
