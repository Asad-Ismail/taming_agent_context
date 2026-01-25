---
name: minimalify
description: Simplify Python code to bare minimum like Andrej Karpathy's mini-projects (nanoGPT, lit-gpt). Remove abstractions, extract shared utilities, eliminate verbosity. Keep it functional, explicit, minimal.
---

# Minimalify - Bare Minimum Python Code

## When to Use
- Code has unnecessary abstractions (classes, wrappers, factories)
- Functions are verbose with too many comments
- Shared utility functions are duplicated across files
- Code feels "over-engineered" for what it does
- You want Andrej Karpathy-style minimal code

## Core Philosophy

**Like mini-projects from Andrej Karpathy:**
- No classes unless necessary (prefer functions)
- No abstract base classes (YAGNI)
- No getters/setters/wrappers
- Explicit is better than implicit
- One file = one purpose
- Shared code goes in `utils.py`

## Anti-Patterns to Remove

### Unnecessary Classes

**BAD - Class wrapper for no reason:**
```python
class DataProcessor:
    def __init__(self, config: dict):
        self.config = config

    def process(self, data: list) -> list:
        return [self._transform(x) for x in data]

    def _transform(self, item: dict) -> dict:
        return {"processed": item["value"] * 2}

# Usage
processor = DataProcessor(config)
result = processor.process(data)
```

**GOOD - Simple function:**
```python
def process_data(data: list) -> list:
    return [{"processed": x["value"] * 2} for x in data]

# Usage
result = process_data(data)
```

### Verbose Docstrings

**BAD - Paragraph docstrings:**
```python
def load_data(file_path: str) -> list[dict]:
    """
    Load data from CSV file into memory for processing.

    This function reads the specified CSV file and parses each row
    into a dictionary using the csv.DictReader. It is important to
    call this function before any data processing operations.

    Args:
        file_path: Path to the CSV file to read

    Returns:
        A list of dictionaries representing the CSV rows
    """
    with open(file_path) as f:
        return list(csv.DictReader(f))
```

**GOOD - Self-documenting code:**
```python
def load_data(path: str) -> list[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))
```

### Abstract Base Classes

**BAD - ABC for single implementation:**
```python
from abc import ABC, abstractmethod

class LLMWrapper(ABC):
    @abstractmethod
    def call(self, messages: list) -> str:
        pass

class OpenAIWrapper(LLMWrapper):
    def call(self, messages: list) -> str:
        return openai.chat.completions.create(messages)
```

**GOOD - Just the function:**
```python
def call_llm(messages: list) -> str:
    return openai.chat.completions.create(messages)
```

### Factory Patterns

**BAD - Factory for two things:**
```python
def create_wrapper(backend: str):
    if backend == "openai":
        return OpenAIWrapper()
    elif backend == "vllm":
        return VLLMWrapper()
    else:
        raise ValueError(f"Unknown backend: {backend}")
```

**GOOD - Direct instantiation:**
```python
# Just create what you need
wrapper = OpenAIWrapper()  # or VLLMWrapper()
```

## Refactoring Patterns

### Extract Shared Utilities

Find duplicated code across files and move to `utils.py`:

**Before - Same code in 3 files:**
```python
# file1.py
def format_output(data: dict) -> str:
    return json.dumps(data, indent=2)

# file2.py
def format_output(data: dict) -> str:
    return json.dumps(data, indent=2)

# file3.py
def format_output(data: dict) -> str:
    return json.dumps(data, indent=2)
```

**After - Shared utility:**
```python
# utils.py
def format_output(data: dict) -> str:
    return json.dumps(data, indent=2)

# file1.py, file2.py, file3.py
from utils import format_output
```

### Inline Single-Use Functions

**Before - Helper used once:**
```python
def _validate_input(data: dict) -> bool:
    return "id" in data and "value" in data

def process_item(item: dict) -> dict:
    if not _validate_input(item):
        raise ValueError("Invalid input")
    return {"result": item["value"] * 2}
```

**After - Inline the check:**
```python
def process_item(item: dict) -> dict:
    if "id" not in item or "value" not in item:
        raise ValueError("Invalid input")
    return {"result": item["value"] * 2}
```

### Remove Configuration Classes

**Before - Config class:**
```python
@dataclass
class Config:
    model: str = "gpt-4"
    temperature: float = 0.1
    max_tokens: int = 1000

config = Config(model="gpt-3.5-turbo")
```

**After - Just variables:**
```python
MODEL = "gpt-3.5-turbo"
TEMPERATURE = 0.1
MAX_TOKENS = 1000
```

## Minimal Code Examples

### File Reading

**Minimal:**
```python
def read_file(path: str) -> str:
    return Path(path).read_text()
```

### HTTP Request

**Minimal:**
```python
async def fetch(url: str) -> dict:
    return httpx.AsyncClient().get(url).json()
```

### Data Processing

**Minimal:**
```python
def process(items: list) -> list:
    return [transform(x) for x in items if x]
```

### Async Loop

**Minimal:**
```python
async def run_all(tasks: list) -> list:
    return await asyncio.gather(*tasks)
```

## When Classes ARE OK

Use classes only when you have:
1. **State management** - Need to maintain state across calls
2. **Multiple related methods** - Operating on same data
3. **Inheritance makes sense** - Real shared behavior

**Example - OK to use class:**
```python
class Cache:
    def __init__(self):
        self.data = {}

    def get(self, key: str) -> Any:
        return self.data.get(key)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
```

## File Organization

**Minimal project structure:**
```
project/
├── main.py          # Entry point
├── utils.py         # Shared utilities
├── config.py        # Constants (if needed)
└── README.md        # Documentation
```

**Multi-file project:**
```
project/
├── main.py
├── train.py
├── models.py
├── utils.py         # ALL shared code
└── data.py
```

## Code Style Checklist

- [ ] No classes for single functions
- [ ] No abstract base classes (YAGNI)
- [ ] No factory patterns
- [ ] No verbose docstrings (code should be self-documenting)
- [ ] No getters/setters
- [ ] Functions under 20 lines
- [ ] Shared code in `utils.py`
- [ ] No comments explaining "what" (only "why" for complex logic)
- [ ] Type hints on function signatures only
- [ ] No configuration classes (use constants or dataclasses)

## References

- [nanoGPT](https://github.com/karpathy/nanoGPT) - ~300 lines, no abstractions
- [lit-gpt](https://github.com/Lightning-AI/lit-gpt) - Minimal GPT implementation
- [micrograd](https://github.com/karpathy/micrograd) - Autograd in 100 lines

## Quick Refactor

1. **Remove all classes** - Convert to functions
2. **Delete docstrings** - Keep code self-documenting
3. **Find duplicated code** - Move to `utils.py`
4. **Inline single-use helpers** - Remove abstraction layer
5. **Flatten structure** - Remove nested helper functions
6. **Use standard library** - No external deps unless critical
