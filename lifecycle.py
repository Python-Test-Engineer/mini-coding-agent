"""Lifecycle hooks for the Nanocode agent.

Hooks let external code observe and react to key moments in an agent's
execution without modifying the agent itself.  Every hook receives the
agent instance as its first argument so it can inspect state.

Usage::

    from src import Agent, Hooks, OpenRouter, tools

    class MyHooks(Hooks):
        def after_brain_response(self, agent, thought):
            print(f"Model used {agent.brain.last_output_tokens} tokens")

    agent = Agent(brain=..., tools=..., hooks=MyHooks())
"""

import json
import os
import sys
from pathlib import Path


class Hooks:
    """Base class for lifecycle hooks.  Override the methods you care about.

    Every method receives the :class:`Agent` instance as ``agent`` so hooks
    can read conversation history, token usage, mode, etc.
    """

    # ── Session ──
    def on_session_start(self, agent):
        """Called once when the REPL session begins."""
        pass

    def on_session_stop(self, agent):
        """Called once when the REPL session ends."""
        pass

    # ── User input ──
    def before_input(self, agent, user_input):
        """Called before the agent processes a user message."""
        pass

    def after_input(self, agent, user_input, output):
        """Called after the agent finishes processing a user message."""
        pass

    # ── Agentic loop ──
    def before_loop(self, agent):
        """Called at the start of the agentic loop for one turn."""
        pass

    def after_loop(self, agent, output):
        """Called when the agentic loop finishes for one turn."""
        pass

    # ── Brain interaction ──
    def before_brain_request(self, agent, conversation):
        """Called immediately before sending the conversation to the LLM.

        ``conversation`` is the list of messages that will be sent.
        """
        pass

    def after_brain_response(self, agent, thought):
        """Called immediately after receiving a response from the LLM.

        ``thought`` is the provider-neutral :class:`Thought` object.
        """
        pass

    # ── Tool execution ──
    def before_tool_execute(self, agent, tool_name, args):
        """Called before each tool is executed."""
        pass

    def after_tool_execute(self, agent, tool_name, result):
        """Called after each tool finishes."""
        pass

    # ── Context compaction ──
    def before_compact(self, agent):
        """Called before the conversation is compacted."""
        pass

    def after_compact(self, agent, summary):
        """Called after compaction finishes.  ``summary`` is the new summary text."""
        pass

    # ── Mode / brain changes ──
    def on_mode_change(self, agent, old_mode, new_mode):
        """Called when the agent switches between *plan* and *act* mode."""
        pass

    def on_brain_switch(self, agent, old_brain_name, new_brain_name):
        """Called when the user switches to a different brain provider."""
        pass

    # ── Errors ──
    def on_error(self, agent, error, phase):
        """Called when an error is caught during agent execution.

        ``phase`` describes where the error happened, e.g.
        ``"handle_input"``, ``"agentic_loop"``, ``"tool_execute"``.
        """
        pass


class SoundHooks(Hooks):
    """Hooks that play audible beeps for loop start / end.

    Uses :func:`winsound.Beep` on Windows and the terminal bell elsewhere.

    Example::

        from src import Agent, SoundHooks
        agent = Agent(brain=..., tools=..., hooks=SoundHooks())
    """

    def _beep(self, tone=None):
        if sys.platform == "win32":
            try:
                import winsound

                if isinstance(tone, int):
                    winsound.Beep(tone, 150)
                elif isinstance(tone, (list, tuple)) and len(tone) == 2:
                    winsound.Beep(*tone)
                else:
                    winsound.Beep(880, 150)
            except Exception as exc:
                print(f"  [SoundHooks] beep failed: {exc}")
        else:
            # macOS / Linux: terminal bell (audible if terminal bell is on)
            print("\a", end="", flush=True)

    def on_session_start(self, agent):
        print("  [SoundHooks] on_session_start -> test beep")
        self._beep((1000, 300))

    def before_loop(self, agent):
        print("  [SoundHooks] before_loop -> beep")
        self._beep((1200, 150))

    def after_loop(self, agent, output):
        print("  [SoundHooks] after_loop -> beep")
        if sys.platform == "win32":
            self._beep((880, 150))
            self._beep((700, 200))
        else:
            self._beep()


SOUNDS_CONFIG = Path(__file__).resolve().parent / "sounds.json"


class MediaHooks(Hooks):
    r"""Hooks that play WAV files through the platform audio player.

    Behaviour is controlled by ``src/sounds.json``, which is re-read on every
    sound so edits take effect in the running session:

    - ``"muted": true`` silences every sound.
    - Each event (``start``, ``loop``, ``done``) has its own ``"enabled"`` flag
      and ``"file"`` path (a full path to a ``.wav`` file).

    Set ``NANOCODE_SOUND=media`` in ``.env`` to turn the hooks on.

    Example::

        from src import Agent, MediaHooks
        agent = Agent(brain=..., tools=..., hooks=MediaHooks())
    """

    def __init__(self, config_path=None):
        self.config_path = Path(config_path) if config_path else SOUNDS_CONFIG

    def _load_config(self):
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  [MediaHooks] cannot read {self.config_path.name}: {exc}")
            return {"muted": True, "events": {}}

    def _play(self, kind):
        config = self._load_config()
        if config.get("muted"):
            print(f"  [MediaHooks] {kind} muted")
            return
        event = config.get("events", {}).get(kind, {})
        if not event.get("enabled", False):
            print(f"  [MediaHooks] {kind} disabled")
            return
        path = event.get("file", "")
        if not path or not os.path.isfile(path):
            print(f"  [MediaHooks] {kind} not found: {path}")
            return
        try:
            if sys.platform == "win32":
                import winsound

                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif sys.platform == "darwin":
                import subprocess

                subprocess.Popen(["afplay", path])
            else:
                import subprocess

                subprocess.Popen(["aplay", "-q", path])
            print(f"  [MediaHooks] {kind} -> {os.path.basename(path)}")
        except Exception as exc:
            print(f"  [MediaHooks] {kind} play failed: {exc}")

    def on_session_start(self, agent):
        print("  [MediaHooks] on_session_start")
        self._play("start")

    def before_loop(self, agent):
        print("  [MediaHooks] before_loop")
        self._play("loop")

    def after_loop(self, agent, output):
        print("  [MediaHooks] after_loop")
        self._play("done")
