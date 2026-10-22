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
        self.console = console or Console()
        path = config_path or Path(__file__).with_name("ui.json")
        self.config: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        self.labels = self.config["labels"]
        self.styles = self.config["styles"]

    def prompt(self, model_name: str) -> str:
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
        line = Text(self.labels["tool"], style=self.styles["tool_label"])
        line.append(f" {name}({json.dumps(arguments)})")
        self.console.print(line)

    def show_code(self, content: str) -> None:
        self.console.print(Syntax(content, "python", theme=self.styles["code_theme"]))

    def show_result(self, result: str) -> None:
        self.console.print(
            Panel(
                result,
                title=Text(self.labels["result"], style=self.styles["result_title"]),
                border_style=self.styles["result_border"],
                padding=(0, 1),
            )
        )

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
            context_text = f"Context: {context:,} input tokens (limit unavailable)"

        self.console.print(Text("-" * 72, style="dim"))
        self.console.print(
            Text(
                f"{context_text}  |  Usage: {total_input:,} in / "
                f"{total_output:,} out  |  Cost so far: ${cost:.6f}",
                style="dim",
            )
        )
