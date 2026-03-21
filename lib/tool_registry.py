import json
from pathlib import Path


class ToolRegistry:
    def __init__(self, tools_dir: str):
        self._tools_dir = Path(tools_dir)
        self._definitions = self._load()

    def _load(self) -> list[dict]:
        definitions = []
        for path in sorted(self._tools_dir.glob("*.json")):
            with open(path) as f:
                definitions.append(json.load(f))
        return definitions

    def get_all_definitions(self) -> list[dict]:
        return self._definitions

    def get_definition(self, name: str) -> dict | None:
        return next((d for d in self._definitions if d["name"] == name), None)

    def get_openai_tools(self) -> list[dict]:
        tools = []
        for defn in self._definitions:
            tools.append({
                "type": "function",
                "function": {
                    "name": defn["name"],
                    "description": defn["description"],
                    "parameters": defn["parameters"],
                },
            })
        return tools
