"""Extension points for observing an agent turn.

Subclass :class:`Hooks` and override the callbacks that are useful to your
application. Callbacks receive an agent context as their first argument, so
they can inspect the current request or session, message history, model step,
and usage metrics without this module depending on the agent implementation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


class Hooks:
    """Base class for optional agent lifecycle callbacks.

    Callbacks are no-ops by default, except session start plays the Windows
    logon sound when its WAV file is available. This lets a workshop
    participant implement only the other events they need, for example to
    record tool use or collect model-usage metrics. ``agent`` is the turn
    request or session context supplied by ``agent.py``; its public attributes
    are ``request``, ``messages``, ``metrics``, and ``step``.
    """

    # A session can contain several user turns. The command-line application
    # calls these once around the complete interactive conversation.
    def on_session_start(self, agent: Any) -> None:
        """Play the Windows logon WAV when an agent session begins."""
        if sys.platform != "win32":
            return

        # Use the standard Windows media folder and keep this hook non-blocking.
        windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        logon_sound = windows_dir / "Media" / "Windows Logon.wav"
        if not logon_sound.is_file():
            return

        try:
            import winsound

            winsound.PlaySound(
                str(logon_sound),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
        except (OSError, RuntimeError):
            # Missing audio devices or inaccessible files should not stop a session.
            return

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
