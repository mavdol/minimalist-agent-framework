import ast
import json
from pathlib import Path

from capsule import run

from lib.tool_registry import ToolRegistry


class Runner:
    def __init__(self, wasm_path: str | Path, registry: ToolRegistry):
        self._wasm = str(wasm_path)
        self._registry = registry

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

        raw = await run(
            file=self._wasm,
            args=[action, *ordered_args],
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
