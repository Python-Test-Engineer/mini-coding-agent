"""Rich console rendering for the mini coding agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


class UI:
    """Render the agent interface using colors and labels from ui.json."""

    def __init__(
        self,
        console: Console | None = None,
        config_path: Path | None = None,
    ) -> None:
        # Resolve the default theme beside this module, not from the launch folder.
        self.console = console or Console()
        path = config_path or Path(__file__).with_name("ui.json")
        self.config: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        self.labels = self.config["labels"]
        self.styles = self.config["styles"]

    def prompt(self, model_name: str) -> str:
        # Rich Text styles the prompt while Console.input still returns plain text.
        prompt = Text()
        prompt.append(
            self.labels["model"].format(model=model_name),
            style=self.styles["input_model"],
        )
        prompt.append(" ")
        prompt.append(self.labels["input"], style=self.styles["input_label"])
        prompt.append(" ")
        prompt.append(
            self.labels["input_indicator"], style=self.styles["input_indicator"]
        )
        prompt.append(" ")
        return self.console.input(prompt)

    def show_start(self, request: str) -> None:
        # Establish the request context once before the model/tool loop begins.
        self.console.rule(
            Text(self.labels["header"], style=self.styles["header"]),
            style=self.styles["header_rule"],
        )
        self.console.print(
            Panel(
                request,
                title=Text(self.labels["request"], style=self.styles["request_title"]),
                border_style=self.styles["request_border"],
                padding=(0, 1),
            )
        )
        self.console.print()

    def show_thought(self, step: int, content: str) -> None:
        # Each model response is shown as a numbered step in the ReAct loop.
        title = self.labels["thought"].format(step=step)
        self.console.print(
            Panel(
                content,
                title=Text(title, style=self.styles["thought_title"]),
                border_style=self.styles["thought_border"],
                padding=(0, 1),
            )
        )

    def show_tool(self, name: str, arguments: dict[str, Any]) -> None:
        # Display the requested call and its JSON arguments before executing it.
        line = Text(self.labels["tool"], style=self.styles["tool_label"])
        line.append(f" {name}({json.dumps(arguments)})")
        self.console.print(line)

    def show_code(self, content: str) -> None:
        # Syntax highlighting makes generated code easier to scan in the demo.
        self.console.print(Syntax(content, "python", theme=self.styles["code_theme"]))

    def show_result(self, result: str) -> None:
        # Tool errors are also results, so the UI can show them consistently.
        self.console.print(
            Panel(
                result,
                title=Text(self.labels["result"], style=self.styles["result_title"]),
                border_style=self.styles["result_border"],
                padding=(0, 1),
            )
        )

    def show_hook_error(self, hook_name: str, error: Exception) -> None:
        """Render hook failures without letting extension code break the UI."""
        self.console.print(
            Panel(
                f"{hook_name}: {error}",
                title=Text(
                    self.labels["hook_error"],
                    style=self.styles["hook_error_title"],
                ),
                border_style=self.styles["hook_error_border"],
                padding=(0, 1),
            )
        )

    def show_lifecycle_event(self, event: str, detail: str = "") -> None:
        """Render a compact, colour-coded trace line for a lifecycle event."""
        event_labels = self.labels["lifecycle_events"]
        event_styles = self.styles["lifecycle_events"]
        # Keep a custom hook name readable even before it has UI configuration.
        label = event_labels.get(event, event.replace("_", " "))
        style = event_styles.get(event, self.styles["lifecycle_prefix"])
        line = Text(self.labels["lifecycle_prefix"], style=self.styles["lifecycle_prefix"])
        # ASCII punctuation keeps the trace legible in legacy Windows consoles.
        line.append(" | ")
        line.append(label, style=style)
        if detail:
            # Lifecycle traces should aid scanning, not dump a complete prompt or result.
            line.append(f" - {detail[:100]}", style=self.styles["lifecycle_detail"])
        self.console.print(line)

    def blank_line(self) -> None:
        self.console.print()

    def show_done(self, metrics: Any = None) -> None:
        self.console.rule(
            Text(self.labels["done"], style=self.styles["done"]),
            style=self.styles["done_rule"],
        )
        self.footer(metrics)

    def show_max_steps(self, metrics: Any = None) -> None:
        self.console.print(
            Text(self.labels["max_steps"], style=self.styles["max_steps"])
        )
        self.footer(metrics)

    def footer(self, metrics: Any = None) -> None:
        # Accept either a metrics dictionary or an object with matching attributes.
        def metric(name: str, default: Any) -> Any:
            if isinstance(metrics, dict):
                return metrics.get(name, default)
            return getattr(metrics, name, default)

        context = metric("last_input_tokens", 0) or 0
        limit = metric("context_limit", None)
        total_input = metric("total_input_tokens", 0) or 0
        total_output = metric("total_output_tokens", 0) or 0
        cost = metric("total_cost", 0.0) or 0.0
        if limit:
            percent = context / limit * 100
            context_text = f"Context: {context:,}/{limit:,} tokens ({percent:.1f}%)"
        else:
            # The completion API may report token usage without exposing model limits.
            context_text = f"Context: {context:,} input tokens (limit unavailable)"

        self.console.print(Text("-" * 72, style="dim"))
        self.console.print(
            Text(
                f"{context_text}  |  Usage: {total_input:,} in / "
                f"{total_output:,} out  |  Cost so far: ${cost:.6f}",
                style="dim",
            )
        )
