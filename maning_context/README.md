# Validating Manus Context Engineering Claims

I read the [Manus blog post](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) and wanted to see if their claims actually hold up. Built a simple agent, ran ablations, measured what matters.

## The Task

Agent cleans a 32K-row CSV (UCI Adult dataset): fill missing values, clip outliers, add a computed column, validate output. Takes 5-10 tool calls. Simple enough to complete reliably, complex enough to show cache/token effects.

## What I Found

4 out of 6 claims checked out. 1 couldn't be tested, 1 doesn't apply to this task.

| Claim | Verdict | What Happened |
|-------|---------|---------------|
| KV-cache matters | ✅ | 4x cost, 2.5x latency when broken |
| Filesystem as memory | ✅ | 225K tokens → rate limit without it |
| Mask tools, don't remove | ✅ | Changing tools mid-run breaks cache |
| Recitation helps focus | ⚠️ | Overhead on short tasks, probably helps at 50+ steps |
| Keep errors visible | ❌ | Couldn't test (task doesn't error reliably) |
| Vary few-shot examples | — | Doesn't apply (single task, no repetitive subtasks to mimic) |

## Results

| Variant | Tests | Steps | OK? | Cache | Cost |
|---------|-------|-------|-----|-------|------|
| **A1** | Baseline | 8 | ✅ | 89% | $0.024 |
| **B1** | Cache breaking | 15 | ❌ | 0% | $0.090 |
| **C1** | No offloading | 5 | ❌ | — | — |
| **D1** | Dynamic tools | 15 | ❌ | 86% | $0.066 |
| **D2** | tool_choice masking | 8 | ✅ | 98% | $0.032 |
| **E2** | No recitation | 4 | ✅ | 75% | $0.014 |

## Reproduce It

```bash
cd maning_context && uv sync
```

### A1: Baseline
Stable prefix, file offloading, todo.md recitation. The "good" config.
```bash
python run_experiment.py --variant A1
```

### B1: Break the Cache  
Fresh UUID at system prompt start each step. Cache goes to 0%.
```bash
python run_experiment.py --variant B1
```

### C1: No Offloading
Large file reads stay in context. Blows up at step 5.
```bash
python run_experiment.py --variant C1
```

### D1: Dynamic Tool Filtering
Remove tools based on state. Cache drops when schema changes.
```bash
python run_experiment.py --variant D1
```

### D2: Tool Choice Masking  
Keep all tools, use `tool_choice` to constrain. Cache stays stable.
```bash
python run_experiment.py --variant D2
```

### E2: No Recitation
Remove todo.md instructions. Agent finishes faster on simple tasks.
```bash
python run_experiment.py --variant E2
```

## What the Numbers Show

**B1 (cache breaking):** Every step pays full prefill cost. 0% cache hit, 4x the cost, agent drifted and failed.

**C1 (no offloading):** Reading a 32K row CSV dumped 200K+ tokens into messages. Hit rate limit immediately.

**D1 vs D2 (tool masking):** When D1 changed the tool list at step 6, cached tokens dropped from 12K to 1.6K. D2 kept tools stable and used `tool_choice`—cache stayed at 14K.

**E2 (no recitation):** Finished in 4 steps vs 8. For an 8-step task, recitation is overhead. For Manus's 50-step average, it probably prevents drift.

## Gotchas I Hit

**Double API calls break your metrics.** If you stream for TTFT then call again for the response, the second call hits the first's cache. B1 showed 95% cache hit until I fixed this.

**Tool schemas are part of the prefix.** Even putting UUID at system message *end* breaks cache when you have tools—they serialize after system in the token stream.

## Couldn't Test With this test case

**Error evidence:** Task doesn't fail in recoverable ways often enough.

**Real logit masking:** OpenAI doesn't expose this. `tool_choice` is close enough for the cache test.

## Doesn't Apply Here

**Few-shot variation:** Manus uses this to prevent pattern mimicry when processing many similar items (like 20 resumes). Our task is a single pipeline—no repetitive subtasks where the agent might copy its own rhythm.

## Bottom Line

Cache stability and file offloading are real and measurable. Breaking either one tanks performance. Recitation matters more as tasks get longer. The Manus techniques work—the hard part is wiring them up cleanly.

## Links

- [Manus Blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [OpenAI Prompt Caching](https://platform.openai.com/docs/guides/prompt-caching)
- [My Prompt Caching Post](https://asad-ismail.github.io/posts/prompt_caching/)
