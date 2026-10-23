"""Verify the terminal UI renders completion and usage details."""

import sys
import unittest
from pathlib import Path

from rich.console import Console

# The app modules remain under src/ and use imports relative to that directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ui import UI


class FooterIntegrationTests(unittest.TestCase):
    def test_023_done_screen_displays_footer(self):
        # Recording lets the test inspect Rich output without a real terminal.
        console = Console(record=True, width=100)
        ui = UI(console=console)

        ui.show_done()

        output = console.export_text()
        self.assertIn("Context:", output)
        self.assertIn("Usage:", output)
        self.assertIn("Cost so far:", output)

    def test_024_max_steps_screen_displays_footer(self):
        console = Console(record=True, width=100)
        ui = UI(console=console)

        ui.show_max_steps()

        self.assertIn("Context:", console.export_text())

    def test_025_done_screen_displays_passed_metrics(self):
        console = Console(record=True, width=120)
        ui = UI(console=console)
        metrics = {
            "last_input_tokens": 1234,
            "context_limit": None,
            "total_input_tokens": 2345,
            "total_output_tokens": 456,
            "total_cost": 0.123456,
        }

        ui.show_done(metrics)

        output = console.export_text()
        self.assertIn("Context: 1,234 input tokens (limit unavailable)", output)
        self.assertIn("Usage: 2,345 in / 456 out", output)
        self.assertIn("Cost so far: $0.123456", output)

    def test_026_context_usage_shows_percentage_when_limit_is_known(self):
        console = Console(record=True, width=120)
        ui = UI(console=console)
        metrics = {
            "last_input_tokens": 2048,
            "context_limit": 8192,
            "total_input_tokens": 2048,
            "total_output_tokens": 100,
            "total_cost": 0.01,
        }

        ui.show_done(metrics)

        self.assertIn("Context: 2,048/8,192 tokens (25.0%)", console.export_text())


if __name__ == "__main__":
    unittest.main()
