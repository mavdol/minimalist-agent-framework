import json
import os
import sys

from openai import AsyncOpenAI

from lib import renderer
from lib.runner import Runner
from lib.tool_registry import ToolRegistry

SYSTEM_PROMPT = """You are a helpful agent. Use your tools to accomplish any task the user asks for.

Always prefer using a tool over asking the user for more information.
Chain multiple tool calls when needed to complete a task.
"""


class Agent:
    def __init__(self, registry: ToolRegistry, runner: Runner):
        base_url = os.getenv("OPENAI_BASE_URL") or None
        self._client = AsyncOpenAI(base_url=base_url)
        self._registry = registry
        self._runner = runner
        self._model = os.getenv("OPENAI_MODEL", "gpt-4o")
        self._messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    async def chat(self, user_input: str) -> None:
        self._messages.append({"role": "user", "content": user_input})
        await self._loop()

    async def _loop(self) -> None:
        while True:
            text, tool_calls = await self._stream_response()

            if not tool_calls:
                break

            for call in tool_calls:
                tool_name = call["function"]["name"]
                tool_args = json.loads(call["function"]["arguments"] or "{}")

                renderer.show_tool_call(tool_name, tool_args)

                confirmed = await renderer.confirm_run()

                if confirmed:
                    result, duration_ms = await self._runner.run(tool_name, tool_args)
                    renderer.show_result(tool_name, result, duration_ms)
                    tool_result_content = result
                else:
                    renderer.show_cancelled(tool_name)
                    tool_result_content = "Execution cancelled by user."
                    sys.exit(1)

                self._messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": tool_result_content,
                })

    async def _stream_response(self) -> tuple[str, list[dict]]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=self._messages,
            tools=self._registry.get_openai_tools(),
            stream=True,
        )

        text_buffer = ""
        tool_calls: dict[int, dict] = {}
        live, buf = renderer.start_stream()

        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                if delta.content:
                    text_buffer += delta.content
                    renderer.update_stream(live, buf, delta.content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls:
                            tool_calls[idx] = {
                                "id": tc.id or "",
                                "type": "function",
                                "function": {"name": tc.function.name or "", "arguments": ""},
                            }
                        else:
                            if tc.id:
                                tool_calls[idx]["id"] = tc.id
                            if tc.function.name:
                                tool_calls[idx]["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls[idx]["function"]["arguments"] += tc.function.arguments
        finally:
            renderer.stop_stream(live)

        assembled_calls = list(tool_calls.values())

        if text_buffer or assembled_calls:
            msg: dict = {"role": "assistant"}
            if text_buffer:
                msg["content"] = text_buffer
            if assembled_calls:
                msg["tool_calls"] = assembled_calls
            self._messages.append(msg)

        return text_buffer, assembled_calls
