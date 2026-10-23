"""Verify lifecycle extensions observe the agent without controlling its UI."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agent
from lifecycle import Hooks
from ui import UI


class RecordingHooks(Hooks):
    """Small test extension that records the public callback contract."""

    def __init__(self):
        self.events = []
        self.context = None

    def before_input(self, context, user_input):
        self.events.append(("before_input", user_input))
        self.context = context

    def before_brain_request(self, context, conversation):
        self.events.append(("before_brain_request", len(conversation)))

    def after_brain_response(self, context, thought):
        self.events.append(("after_brain_response", thought["content"]))

    def after_loop(self, context, output):
        self.events.append(("after_loop", output))

    def after_input(self, context, user_input, output):
        self.events.append(("after_input", user_input, output))


class LifecycleIntegrationTests(unittest.TestCase):
    def test_003_hooks_receive_turn_context_in_lifecycle_order(self):
        recorded = RecordingHooks()
        console = Console(record=True, width=120)
        reply = {"choices": [{"message": {"content": "Finished", "tool_calls": []}}]}

        with patch("agent.ui", UI(console=console)), patch(
            "agent.chat", return_value=reply
        ):
            agent.agent_loop("test request", lifecycle_hooks=recorded)

        self.assertEqual(
            recorded.events,
            [
                ("before_input", "test request"),
                ("before_brain_request", 2),
                ("after_brain_response", "Finished"),
                ("after_loop", "Finished"),
                ("after_input", "test request", "Finished"),
            ],
        )
        self.assertEqual(recorded.context.request, "test request")
        self.assertEqual(recorded.context.step, 1)
        output = console.export_text()
        self.assertIn("lifecycle", output)
        self.assertIn("input received", output)
        self.assertIn("model request", output)
        self.assertIn("model response", output)
        self.assertIn("agent loop finished", output)

    def test_004_a_failing_hook_is_reported_without_stopping_the_agent(self):
        class BrokenHooks(Hooks):
            def before_loop(self, context):
                raise RuntimeError("hook problem")

        console = Console(record=True, width=120)
        reply = {"choices": [{"message": {"content": "Finished", "tool_calls": []}}]}

        with patch("agent.ui", UI(console=console)), patch(
            "agent.chat", return_value=reply
        ):
            agent.agent_loop("test request", lifecycle_hooks=BrokenHooks())

        output = console.export_text()
        self.assertIn("lifecycle hook error", output)
        self.assertIn("Finished", output)


if __name__ == "__main__":
    unittest.main()
