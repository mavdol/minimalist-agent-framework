# Minimalist Agent Framework

A minimalist agent framework where tools are JSON definitions. Each tool runs inside a WebAssembly sandbox.

## How it works

**Tool definitions** live as JSON files in `tools/`. Each one declares the tool's name, parameters, and sandbox constraints — no implementation required.

**At startup**, `SandboxBuilder` reads all definitions and compiles them into a single `.wasm` binary via [Capsule](https://github.com/mavdol/capsule). The result is cached and only recompiled when a definition changes.

**At call time**, `Runner` looks up a cached Python implementation in `.cache/tool_impls.json`. If none exists, it asks the LLM to write one and saves it for next time.

**Execution** happens inside the WASM sandbox, constrained by whatever the tool's JSON declares (`allowed_files`, `allowed_hosts`, `ram`, `timeout`, etc.).

## Setup

```bash
pip install -r requirements.txt
python3 main.py
```

Environment variables:

```bash
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
```

## Defining a tool

Create a file in `tools/<name>.json`:

```json
{
    "name": "my_tool",
    "description": "What this tool does.",
    "parameters": {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "The input value."
            }
        },
        "required": ["input"]
    },
    "capsule": {
        "compute": "LOW",
        "ram": "64MB",
        "timeout": "10s",
        "max_retries": 1,
        "allowed_files": [],
        "allowed_hosts": []
    }
}
```

## Built-in tools

| Tool | Description |
|---|---|
| `execute_code` | Runs arbitrary Python code |
| `read_file` | Reads a file from disk |
| `write_files` | Writes content to a file |
| `list_files` | Lists files in a directory |

To learn more about how sandboxing works, see the [Capsule](https://github.com/mavdol/capsule) repository.
