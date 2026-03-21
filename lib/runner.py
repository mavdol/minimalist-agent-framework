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

        # Build positional args in the order defined by the tool's parameters schema
        defn = self._registry.get_definition(tool_name)
        param_order = list(defn["parameters"]["properties"].keys()) if defn else list(tool_args.keys())
        ordered_args = [tool_args[p] for p in param_order if p in tool_args]

        envelope = await run(
            file=self._wasm,
            args=[action, *ordered_args],
        )

        duration_ms: int | None = None
        if isinstance(envelope, dict):
            execution = envelope.get("execution", {})
            duration_ms = execution.get("duration_ms")

            if envelope.get("success"):
                result = envelope.get("result")
                return (str(result) if result is not None else "(no output)"), duration_ms
            else:
                err = envelope.get("error") or {}
                if isinstance(err, dict):
                    msg = f"{err.get('error_type', 'Error')}: {err.get('message', 'unknown error')}"
                else:
                    msg = str(err)
                return msg, duration_ms

        # Fallback — capsule returned something unexpected
        return str(envelope), duration_ms
