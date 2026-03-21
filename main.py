import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from lib import renderer
from lib.agent import Agent
from lib.runner import Runner
from lib.sandbox_builder import SandboxBuilder
from lib.tool_registry import ToolRegistry


async def main() -> None:
    registry = ToolRegistry("./tools")

    builder = SandboxBuilder(registry, cache_dir=".cache")
    try:
        wasm_path = builder.build(on_step=renderer.build_step)
    except RuntimeError as e:
        renderer.show_error(str(e))
        sys.exit(1)

    runner = Runner(wasm_path, registry)
    agent = Agent(registry, runner)

    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        await agent.chat(user_input)
        return

    renderer.show_ready()
    while True:
        try:
            user_input = await renderer.prompt("> ")
        except (EOFError, KeyboardInterrupt):
            break

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        try:
            await agent.chat(user_input)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    asyncio.run(main())
