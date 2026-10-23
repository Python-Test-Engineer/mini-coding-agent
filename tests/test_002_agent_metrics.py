"""Verify usage metrics flow from model replies into the UI footer."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

# The app modules remain under src/ and use imports relative to that directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agent
from ui import UI


class UsageMetricTests(unittest.TestCase):
    def test_003_work_directory_is_anchored_at_repository_root(self):
        expected = Path(agent.__file__).resolve().parent.parent / "work"

        self.assertEqual(agent.WORKDIR, expected)

    def test_004_accumulates_input_output_and_cost_across_responses(self):
        metrics = {
            "last_input_tokens": 0,
            "context_limit": None,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost": 0.0,
        }

        # Each model reply contributes billable prompt/completion usage.
        agent._accumulate_usage(
            metrics, {"prompt_tokens": 10, "completion_tokens": 3, "cost": 0.01}
        )
        agent._accumulate_usage(
            metrics, {"prompt_tokens": 8, "completion_tokens": 2, "cost": 0.02}
        )

        self.assertEqual(metrics["last_input_tokens"], 8)
        self.assertEqual(metrics["total_input_tokens"], 18)
        self.assertEqual(metrics["total_output_tokens"], 5)
        self.assertAlmostEqual(metrics["total_cost"], 0.03)

    def test_005_missing_usage_fields_leave_totals_unchanged(self):
        metrics = {
            "last_input_tokens": 7,
            "context_limit": None,
            "total_input_tokens": 12,
            "total_output_tokens": 4,
            "total_cost": 0.02,
        }

        # Compatible API providers may omit usage details from a reply.
        agent._accumulate_usage(metrics, {})

        self.assertEqual(metrics["last_input_tokens"], 7)
        self.assertEqual(metrics["total_input_tokens"], 12)
        self.assertEqual(metrics["total_output_tokens"], 4)
        self.assertAlmostEqual(metrics["total_cost"], 0.02)

    def test_006_agent_passes_response_usage_to_the_footer(self):
        console = Console(record=True, width=120)
        reply = {
            "choices": [{"message": {"content": "Finished", "tool_calls": []}}],
            "usage": {
                "prompt_tokens": 321,
                "completion_tokens": 12,
                "cost": 0.0042,
            },
        }

        # Patch the network boundary so this exercises the real loop without an API call.
        with (
            patch("agent.ui", UI(console=console)),
            patch("agent.chat", return_value=reply),
        ):
            agent.agent_loop("test request")

        output = console.export_text()
        self.assertIn("Context: 321 input tokens (limit unavailable)", output)
        self.assertIn("Usage: 321 in / 12 out", output)
        self.assertIn("Cost so far: $0.004200", output)


if __name__ == "__main__":
    unittest.main()
