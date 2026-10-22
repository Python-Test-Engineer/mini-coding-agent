"""Extension points for observing an agent turn.

Subclass :class:`Hooks` and override the callbacks that are useful to your
application.  Callbacks receive the turn context as their first argument, so
they can inspect the request, messages, current step, and usage metrics
without the hook module depending on the agent or UI implementation.
"""

from __future__ import annotations

from typing import Any


class Hooks:
    """Base class for optional agent lifecycle callbacks.

    Every callback is intentionally a no-op.  This lets a workshop participant
    implement only the events they need, for example to record tool use or
    collect model-usage metrics.  ``agent`` is the turn context supplied by
    ``agent.py``; its public attributes are ``request``, ``messages``,
    ``metrics``, and ``step``.
    """

    # A process can contain several turns.  The command-line application calls
    # these once around its single turn; an interactive REPL could reuse them
    # around its longer-lived session.
    def on_session_start(self, agent: Any) -> None:
        """Called when an agent session begins."""

    def on_session_stop(self, agent: Any) -> None:
        """Called when an agent session ends."""

    def before_input(self, agent: Any, user_input: str) -> None:
        """Called before the turn processes a user request."""

    def after_input(self, agent: Any, user_input: str, output: str) -> None:
        """Called after the turn finishes processing a user request."""

    def before_loop(self, agent: Any) -> None:
        """Called at the beginning of the model/tool loop."""

    def after_loop(self, agent: Any, output: str) -> None:
        """Called when the model/tool loop finishes."""

    def before_brain_request(self, agent: Any, conversation: list[dict]) -> None:
        """Called immediately before the conversation is sent to the model."""

    def after_brain_response(self, agent: Any, thought: dict) -> None:
        """Called immediately after a provider response is received."""

    def before_tool_execute(
        self, agent: Any, tool_name: str, arguments: dict
    ) -> None:
        """Called before a requested tool is executed."""

    def after_tool_execute(self, agent: Any, tool_name: str, result: str) -> None:
        """Called after a requested tool finishes, including failures."""

    def before_compact(self, agent: Any) -> None:
        """Reserved for a future conversation-compaction step."""

    def after_compact(self, agent: Any, summary: str) -> None:
        """Reserved for after a future conversation-compaction step."""

    def on_mode_change(self, agent: Any, old_mode: str, new_mode: str) -> None:
        """Reserved for a future plan/act mode switch."""

    def on_brain_switch(
        self, agent: Any, old_brain_name: str, new_brain_name: str
    ) -> None:
        """Reserved for a future model-provider switch."""

    def on_error(self, agent: Any, error: Exception, phase: str) -> None:
        """Called when the host catches an error during the named phase."""
