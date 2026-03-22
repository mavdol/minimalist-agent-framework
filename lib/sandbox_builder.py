import hashlib
import json
import subprocess
import textwrap
from collections.abc import Callable
from pathlib import Path

from lib.tool_registry import ToolRegistry

_EXECUTOR_BODY = textwrap.dedent("""\
    tree = ast.parse(code)
    _globals = {params_dict}

    old_stdout = sys.stdout
    sys.stdout = StringIO()

    result = None
    try:
        if tree.body:
            *stmts, last = tree.body
            if stmts:
                exec(compile(ast.Module(body=stmts, type_ignores=[]), "<code>", "exec"), _globals)
            if isinstance(last, ast.Expr):
                result = eval(compile(ast.Expression(body=last.value), "<code>", "eval"), _globals)
            else:
                exec(compile(ast.Module(body=[last], type_ignores=[]), "<code>", "exec"), _globals)
    finally:
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

    if result is not None:
        return (output + "\\n" + str(result)).strip()
    return output.strip() if output.strip() else None
""")


class SandboxBuilder:
    def __init__(self, registry: ToolRegistry, cache_dir: str = ".cache"):
        self._registry = registry
        self._cache_dir = Path(cache_dir)
        self._sandbox_py = self._cache_dir / "capsule_sandbox.py"
        self._sandbox_wasm = self._cache_dir / "capsule_sandbox.wasm"
        self._hash_file = self._cache_dir / "sandbox.hash"

    def build(self, on_step: Callable[[str], None] | None = None) -> Path:
        self._cache_dir.mkdir(exist_ok=True)
        current_hash = self._compute_hash()

        if self.is_cache_valid(current_hash):
            if on_step:
                on_step("Sandboxed tools ready (cached)")
        else:
            if on_step:
                on_step(f"Generating tools ({len(self._registry.get_all_definitions())} tools)…")
            self._generate_source()
            if on_step:
                on_step("Compiling to WebAssembly…")
            self._compile()
            self._hash_file.write_text(current_hash)
            if on_step:
                on_step("Sandboxed tools ready")

        return self._sandbox_wasm

    def is_cache_valid(self, current_hash: str | None = None) -> bool:
        if not self._sandbox_wasm.exists() or not self._hash_file.exists():
            return False
        if current_hash is None:
            current_hash = self._compute_hash()
        return self._hash_file.read_text().strip() == current_hash

    def _compute_hash(self) -> str:
        h = hashlib.sha256()
        for defn in self._registry.get_all_definitions():
            h.update(json.dumps(defn, sort_keys=True).encode())
        return h.hexdigest()

    def _generate_source(self) -> None:
        lines = [
            "# .cache/capsule_sandbox.py — AUTO-GENERATED, DO NOT EDIT",
            "",
            "from capsule import task",
            "import ast, sys",
            "from io import StringIO",
            "",
        ]

        for defn in self._registry.get_all_definitions():
            lines += self._generate_task(defn)
            lines.append("")

        lines += self._generate_dispatcher()
        self._sandbox_py.write_text("\n".join(lines) + "\n")

    def _generate_task(self, defn: dict) -> list[str]:
        capsule = defn.get("capsule", {})
        name = defn["name"]

        task_kwargs = []
        task_name = "".join(w.capitalize() for i, w in enumerate(name.split("_")))
        task_name = task_name[0].lower() + task_name[1:]
        task_kwargs.append(f'name="{task_name}"')

        if "compute" in capsule:
            task_kwargs.append(f'compute="{capsule["compute"]}"')
        if "ram" in capsule:
            task_kwargs.append(f'ram="{capsule["ram"]}"')
        if "timeout" in capsule:
            task_kwargs.append(f'timeout="{capsule["timeout"]}"')
        if "max_retries" in capsule:
            task_kwargs.append(f'max_retries={capsule["max_retries"]}')
        if "allowed_files" in capsule:
            task_kwargs.append(f'allowed_files={json.dumps(capsule["allowed_files"])}')
        if "allowed_hosts" in capsule:
            task_kwargs.append(f'allowed_hosts={json.dumps(capsule["allowed_hosts"])}')

        props = defn.get("parameters", {}).get("properties", {})
        sig_parts = []
        for param, meta in props.items():
            py_type = _json_type_to_py(meta.get("type", "str"))
            sig_parts.append(f"{param}: {py_type}")

        if name == "execute_code":
            sig = ", ".join(sig_parts)
            params_dict = "{}"
        else:
            sig = "code: str" + (", " + ", ".join(sig_parts) if sig_parts else "")
            params_dict = "{" + ", ".join(f'"{p}": {p}' for p in props) + "}"

        body_lines = _EXECUTOR_BODY.replace("{params_dict}", params_dict).splitlines()

        decorator = f"@task({', '.join(task_kwargs)})"
        lines = [decorator, f"def {name}({sig}):"]
        for body_line in body_lines:
            lines.append(f"    {body_line}" if body_line else "")

        return lines

    def _generate_dispatcher(self) -> list[str]:
        lines = [
            '@task(name="main", compute="HIGH")',
            "def main(action: str, *args):",
        ]
        for defn in self._registry.get_all_definitions():
            action = defn["name"].upper()
            fn = defn["name"]
            lines.append(f'    if action == "{action}":')
            lines.append(f"        return {fn}(*args)")
        lines.append('    return {"error": f"Unknown action: {action}"}')
        return lines

    def _compile(self) -> None:
        result = subprocess.run(
            ["capsule", "build", str(self._sandbox_py), "--export"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"capsule build failed:\n{result.stderr or result.stdout}"
            )


def _json_type_to_py(json_type: str) -> str:
    return {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}.get(
        json_type, "str"
    )


