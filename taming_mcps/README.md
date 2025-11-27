# Taming Agent Context: Code Mode vs Traditional MCP

This project demonstrates two approaches to using MCP (Model Context Protocol) tools and compares their efficiency and scalability.

**Architecture Note:** This project implements the "File Tree" discovery pattern described in [Anthropic's Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) article.

## Approaches

### 1. Traditional Mode
- All MCP tools are loaded directly into the LLM context
- Every tool definition is sent with each request
- Simple, but hits hard scaling limits

### 2. Code Mode
- LLM discovers and calls tools via Python code execution
- Only a single `run_python` tool in context
- Agent explores `./servers/` directory to find available tools
- Scales to unlimited tools without context overflow

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

### The Scalability Wall
 |

**Key Insight:** Prompt caching reduces the *cost* of tool definitions but doesn't reduce their *capacity* usage. At scale, traditional mode physically runs out of context space, leaving no room for actual conversations, documents, or RAG data.

### Why This Matters Beyond Tokens

**1. Context Capacity:** The primary benefit isn't token cost—it's breaking the context window ceiling. Enterprise agents connecting to 1,000+ tools would consume the entire context window with just definitions.

**2. Intermediate Data Handling:** Traditional mode forces all data through the model (e.g., reading a 10MB CSV to find one row). Code mode processes data in the Python sandbox, keeping context clean.

**3. Model Competence:** LLMs are pre-trained on millions of open-source code repositories but fine-tuned on synthetic tool-calling data. They're naturally better at writing Python logic (loops, filtering, complex operations) than predicting rigid JSON tool schemas.

## Trade-offs

### Traditional Mode Advantages
- **Faster for simple queries:** Single round-trip with direct tool calls (2 turns vs 6)
- **Better out-of-box control:** Models explicitly trained for function calling
- **Simpler infrastructure:** No code execution environment needed
- **Works with prompt caching:** Cached tool definitions become very cheap (90% discount)

### Traditional Mode Critical Limitations
- **Hard capacity ceiling:** 500+ tools consume entire context window, regardless of caching
- **Intermediate data bloat:** All tool results must pass through context (e.g., full CSV files)
- **Limited reasoning:** Cannot perform complex logic like filtering, loops, or data transformations
- **Synthetic training:** Models fine-tuned on contrived tool-use examples, not real-world APIs

### Code Mode Advantages
- **Unlimited scale:** Handles 1,000+ tools without context impact
- **Efficient data handling:** Process large datasets in sandbox, return only relevant results
- **Superior reasoning:** Leverage model's deep pre-training on real open-source code
- **Native complexity:** Loops, conditionals, filtering—all handled naturally in Python
- **Intermediate results stay clean:** Data processing happens in execution environment

### Code Mode Limitations
- **Slower for simple queries:** Multiple discovery turns increase latency
- **Instruction following challenges:** Models trained on code may ignore tool discovery prompts
  - Example: Time queries default to `datetime` instead of discovering MCP time tools
  - Models prefer familiar stdlib patterns over new tool exploration
- **Infrastructure overhead:** Requires secure code execution environment with sandboxing
- **Security critical:** `run_python` is essentially RCE—sandboxing is mandatory, not optional

### Mitigation Strategies
- **Controlled execution environment:** Restrict available modules and enforce tool discovery
- **Explicit prohibitions:** Block stdlib alternatives (e.g., `datetime`, `pytz`) in system prompts
- **Mandatory workflows:** Require step-by-step discovery before tool usage
- **Resource limits and monitoring:** Sandbox with timeouts, memory limits, and audit logs

### When to Use Each Approach

**Use Traditional Mode when:**
- You have < 100 tools and can leverage prompt caching
- Simple, single-step queries are the primary use case
- Minimizing latency is critical
- Code execution infrastructure is unavailable

**Use Code Mode when:**
- You need to scale beyond 500 tools
- Working with large datasets or intermediate results
- Complex multi-step workflows with logic/filtering
- You can invest in proper execution environment infrastructure

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