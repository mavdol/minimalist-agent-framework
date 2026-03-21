import asyncio

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

console = Console()
_session = PromptSession(history=InMemoryHistory())


async def prompt(text: str = "> ") -> str:
    return await _session.prompt_async(text)


def start_stream() -> tuple[Live, list[str]]:
    buffer: list[str] = [""]
    live = Live(Markdown(""), console=console, refresh_per_second=15)
    live.start()
    return live, buffer


def update_stream(live: Live, buffer: list[str], chunk: str) -> None:
    buffer[0] += chunk
    live.update(Markdown(buffer[0]))


def stop_stream(live: Live) -> None:
    live.stop()


def show_tool_call(tool_name: str, code: str) -> None:
    syntax = Syntax(code, "python", theme="monokai", word_wrap=True)
    console.print(Panel(syntax, title=tool_name, border_style="dim"))


async def confirm_run() -> bool:
    try:
        answer = await _session.prompt_async("  Run? [y/n]: ")
        return answer.strip().lower() in ("y", "yes", "")
    except (EOFError, KeyboardInterrupt):
        return False


def show_result(tool_name: str, result: str) -> None:
    display = result if len(result) <= 200 else result[:200] + "…"
    console.print(f"  [dim]{tool_name}[/dim]  →  {display}")


def show_cancelled(tool_name: str) -> None:
    console.print(f"  [dim]{tool_name}  →  cancelled[/dim]")


def show_error(message: str) -> None:
    console.print(f"[red]Error:[/red] {message}")


def build_step(message: str) -> None:
    console.print(f"  [dim]{message}[/dim]")


def show_ready() -> None:
    console.print("[dim]Type your message or 'exit' to quit.[/dim]\n")
