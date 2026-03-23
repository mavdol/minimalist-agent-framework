import ast
import json
import os
from pathlib import Path

import openai
from capsule import run

from lib.tool_registry import ToolRegistry


class Runner:
    def __init__(self, wasm_path: str | Path, registry: ToolRegistry, cache_dir: str | Path = ".cache"):
        self._wasm = str(wasm_path)
        self._registry = registry
        self._impls_file = Path(cache_dir) / "tool_impls.json"
        self._impls: dict[str, str] = self._load_impls()

    def _load_impls(self) -> dict[str, str]:
        if self._impls_file.exists():
            return json.loads(self._impls_file.read_text())
        return {}

    def _save_impls(self) -> None:
        self._impls_file.write_text(json.dumps(self._impls, indent=2))

    def _get_impl(self, defn: dict) -> str:
        name = defn["name"]
        if name in self._impls:
            return self._impls[name]

        props = defn.get("parameters", {}).get("properties", {})
        params_desc = "\n".join(
            f"  - {p} ({meta.get('type', 'str')}): {meta.get('description', '')}"
            + (" [JSON-encoded string — use json.loads() to parse]" if meta.get("type") in ("array", "object") else "")
            for p, meta in props.items()
        )
        hint = f"- {defn['hint']}\n" if "hint" in defn else ""
        prompt = (
            f"Write a Pure Python snippet that implements: {defn['description']}\n"
            f"Available variables (already in scope):\n{params_desc}\n\n"
            "Rules:\n"
            "- Do not use any external libraries\n"
            f"{hint}"
            "- The last expression must be a str (use join, str(), etc)\n"
            "- Never return a list or dict\n"
            "- No external libraries or libraries using C extensions are allowed"
        )
        client = openai.OpenAI(base_url=os.getenv("OPENAI_BASE_URL") or None)
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        code = response.choices[0].message.content.strip()
        if code.startswith("```"):
            code = "\n".join(
                line for line in code.splitlines()
                if not line.startswith("```")
            ).strip()

        self._impls[name] = code
        self._save_impls()
        return code

    async def run(self, tool_name: str, tool_args: dict) -> tuple[str, int | None]:
        """
        Execute a tool call inside the Capsule sandbox.

        Returns (result_str, duration_ms).
        On failure, result_str is an error description.
        """
        action = tool_name.upper()

        defn = self._registry.get_definition(tool_name)
        param_order = list(defn["parameters"]["properties"].keys()) if defn else list(tool_args.keys())
        ordered_args = [tool_args[p] for p in param_order if p in tool_args]

        if tool_name != "execute_code" and defn:
            impl_code = self._get_impl(defn)
            ordered_args = [impl_code, *ordered_args]

        str_args = [
            arg if isinstance(arg, str) else json.dumps(arg)
            for arg in ordered_args
        ]
        raw = await run(
            file=self._wasm,
            args=[action, *str_args],
        )

        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                try:
                    raw = ast.literal_eval(raw)
                except (ValueError, SyntaxError):
                    return raw, None

        success = _get(raw, "success")
        execution = _get(raw, "execution") or {}
        duration_ms: int | None = _get(execution, "duration_ms")

        if success:
            inner = _get(raw, "result")
            if isinstance(inner, dict):
                if not _get(inner, "success"):
                    err = _get(inner, "error") or {}
                    msg = err.get("message", "unknown error") if isinstance(err, dict) else str(err)
                    return msg, duration_ms
                result = _get(inner, "result")
                inner_exec = _get(inner, "execution") or {}
                duration_ms = _get(inner_exec, "duration_ms") or duration_ms
            else:
                result = inner
            return (str(result) if result is not None else "(no output)"), duration_ms

        err = _get(raw, "error") or {}
        if isinstance(err, dict):
            msg = f"{err.get('error_type', 'Error')}: {err.get('message', 'unknown error')}"
        elif hasattr(err, "error_type"):
            msg = f"{err.error_type}: {err.message}"
        else:
            msg = str(err) if err else "unknown error"
        return msg, duration_ms


def _get(obj, key: str):
    """Get a value from a dict or an attribute-based object."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
