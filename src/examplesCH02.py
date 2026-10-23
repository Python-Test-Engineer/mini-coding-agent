"""Offline demonstrations of lifecycle hooks and the constrained runner.

Run from the ``src`` directory with ``uv run python examplesCH02.py``. Neither
example calls the model API. The sandbox example copies this script and a
small greeting program into the repository's ``work/`` directory, then shows
that a write to the repository root is rejected.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from lifecycle import Hooks
from sandbox import (
    ConstrainedLocalRunner,
    SandboxCommandError,
    SandboxPathError,
    SandboxWorkspace,
)

console = Console()


def show_hook(message: str) -> None:
    """Print hook output with a distinct Rich style."""
    line = Text("[hook] ", style="bold magenta")
    line.append(message)
    console.print(line)


def show_status(
    label: str,
    detail: str,
    *,
    passed: bool,
    detail_style: str | None = None,
) -> None:
    """Print status in green or red, with optional detail coloring."""
    line = Text()
    line.append(f"{label} ", style="bold green" if passed else "bold red")
    line.append(detail, style=detail_style or (None if passed else "red"))
    console.print(line)


def run_example(
    name: str,
    description: str,
    example: Callable[[], None],
) -> None:
    """Describe an example and report its overall result in color."""
    console.print()
    console.print(
        Panel(description, title=f"[bold cyan]{name}[/]", border_style="cyan")
    )

    try:
        example()
    except Exception as error:
        show_status("FAIL", f"{type(error).__name__}: {error}", passed=False)
    else:
        show_status("PASS", f"{name} completed successfully.", passed=True)


class StudentHooks(Hooks):
    """Print a short message when selected lifecycle events occur."""

    def before_input(self, agent, user_input):
        show_hook(f"starting request: {user_input!r}")

    def before_tool_execute(self, agent, tool_name, arguments):
        show_hook(f"about to call {tool_name} with {arguments}")

    def after_tool_execute(self, agent, tool_name, result):
        show_hook(f"{tool_name} returned: {result}")

    def on_error(self, agent, error, phase):
        show_hook(f"caught {type(error).__name__} during {phase}: {error}")

    def after_input(self, agent, user_input, output):
        show_hook(f"request finished: {output!r}")


def demonstrate_hooks() -> None:
    """Call sample hooks directly to show their inputs without an API call."""
    # The harness passes a context object as the first argument to each hook.
    # This stand-in provides fields that hooks commonly inspect.
    context = SimpleNamespace(request="make a greeting", step=1, metrics={})
    hooks = StudentHooks()

    # The real agent loop invokes callbacks around these lifecycle events.
    hooks.before_input(context, context.request)
    hooks.before_tool_execute(context, "write_file", {"path": "hello.py"})
    hooks.after_tool_execute(context, "write_file", "Created hello.py")

    # Simulate an error callback so students can see how a rejection is reported.
    hooks.on_error(context, PermissionError("example rejection"), "tool_execute")
    hooks.after_input(context, context.request, "Finished")


def demonstrate_sandbox() -> None:
    """Show allowed and rejected file and command operations."""
    # Use the repository's real work/ and logs/ folders so the files remain
    # visible after the demo exits. Writes through this workspace are still
    # checked before they reach the filesystem.
    project_root = Path(__file__).resolve().parents[1]
    workspace = SandboxWorkspace(project_root / "work", project_root / "logs")
    runner = ConstrainedLocalRunner(workspace)

    # PASS: save this running example into work/ so students can inspect it.
    this_file = Path(__file__).read_text(encoding="utf-8")
    show_status(
        "PASS write",
        workspace.write_file("examples.py", this_file),
        passed=True,
    )
    console.print(
        Panel(
            str(workspace.resolve_read_path("examples.py")),
            title="Saved copy",
            border_style="green",
            expand=False,
        )
    )
    console.print(
        "First line:",
        workspace.read_file("examples.py").splitlines()[0],
        markup=False,
    )

    # PASS: save a small Python file in work/, then run it with the allowlisted
    # Python command. Both generated files remain in work/ after this demo.
    created = workspace.write_file(
        "hello.py",
        'print("Hello from work/")\n',
    )
    show_status("PASS write", created, passed=True)
    show_status("PASS read", workspace.read_file("hello.py").strip(), passed=True)
    console.print(Panel(
        runner.run("python hello.py"),
        title="PASS command",
        border_style="green",
        expand=False,
    ))

    # This write should fail: from work/, ../goodbye.py would target the
    # repository root. The workspace rejects it, so no root file is created.
    try:
        workspace.write_file("../goodbye.py", 'print("This should not be saved")\n')
    except SandboxPathError as error:
        show_status(
            "PASS root write was rejected",
            str(error),
            passed=True,
            detail_style="red",
        )
    else:
        raise AssertionError("The sandbox allowed a write outside work/.")

    # This command should fail because shell operators are rejected before
    # a process starts.
    try:
        runner.run("python hello.py & whoami")
    except SandboxCommandError as error:
        show_status(
            "PASS shell operator was rejected",
            str(error),
            passed=True,
            detail_style="red",
        )
    else:
        raise AssertionError("The runner allowed a shell operator.")

    # This command should fail because git is not in the runner's allowlist.
    try:
        runner.run("git status")
    except SandboxCommandError as error:
        show_status(
            "PASS unapproved program was rejected",
            str(error),
            passed=True,
            detail_style="red",
        )
    else:
        raise AssertionError("The runner allowed an unapproved program.")


def main() -> None:
    """Run both offline workshop demonstrations."""
    run_example(
        "Lifecycle hooks",
        "Calls the sample lifecycle callbacks directly and prints the event data "
        "they receive, without making a model API call.",
        demonstrate_hooks,
    )
    run_example(
        "Sandbox",
        "Writes and reads files inside work/, runs an allowed Python command, "
        "and confirms that unsafe paths and commands are rejected.",
        demonstrate_sandbox,
    )


if __name__ == "__main__":
    main()
