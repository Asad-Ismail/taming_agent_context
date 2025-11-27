# Taming Agent Context: Code Mode vs Traditional MCP

This project demonstrates two approaches to using MCP (Model Context Protocol) tools and compares their token efficiency.

## Approaches

### 1. Traditional Mode
- All MCP tools are loaded directly into the LLM context
- Every tool definition is sent with each request
- Simple, but token-intensive

### 2. Code Mode
- LLM discovers and calls tools via Python code execution
- Only a single `run_python` tool in context
- Agent explores `./servers/` directory to find available tools
- Significantly more token-efficient

## Token Usage Comparison

**Test Query:** "Get Current Time of Amsterdam"  
**Available Tools:** 60 MCP tools across 5 servers (time, git, github, sqlite, filesystem)

### Results

| Mode | Turns | Input Tokens | Output Tokens | Total Tokens | Tools in Context |
|------|-------|--------------|---------------|--------------|------------------|
| **Traditional** | 2 | 8,781 | 48 | **8,829** | 60 |
| **Code Mode** | 6 | 4,234 | 174 | **4,408** | 1 |

**Token Savings: ~50% (4,421 tokens saved)**

### Important Notes

- This test uses a **single instruction with a single tool call**
- **Savings scale dramatically with complexity:**
  - Multi-step queries requiring multiple tool calls
  - Complex workflows with conditional logic
  - Scenarios where only a subset of available tools are needed
- As tool count increases, traditional mode's context overhead grows linearly
- Code mode maintains constant low overhead regardless of available tools

## Trade-offs

### Traditional Mode Advantages
- **Better control:** Agents are explicitly trained to use tools via function calling
- **More reliable:** Tool definitions in context ensure proper usage
- **Predictable behavior:** Clear tool schemas guide the model

### Code Mode Limitations
- **Less control:** Agent can write arbitrary Python code instead of using tools
- **Instruction following issues:** Agents trained on large code datasets may ignore system/user instructions
  - Example: Time queries often default to `datetime` module instead of MCP time tools
  - Models prefer familiar stdlib patterns over discovering new tools
- **Requires stronger prompting:** Need explicit prohibitions and mandatory workflows

### Mitigation Strategies
- **Polished code execution environment:** Restrict available modules and enforce tool discovery
- **Explicit prohibitions:** Block stdlib alternatives (e.g., `datetime`, `pytz`) in prompts
- **Mandatory workflows:** Require step-by-step discovery before tool usage
- **Controlled sandbox:** Limit what can be imported or executed

**Recommendation:** Code mode works best when you can afford the engineering effort to build a controlled execution environment that enforces tool usage patterns.

## Usage

1. **Build the tool registry:**
   ```bash
   python build_registry.py
   ```

2. **Run comparison:**
   ```bash
   python compare_token_usage.py
   ```

3. **Run individual modes:**
   ```bash
   python traditional_mode.py
   python code_mode.py
   ```

## References

Taking info from these two main blogs:

- https://www.anthropic.com/engineering/code-execution-with-mcp
- https://blog.cloudflare.com/code-mode/