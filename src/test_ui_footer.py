import unittest

from rich.console import Console

from ui import UI


class FooterIntegrationTests(unittest.TestCase):
    def test_done_screen_displays_footer(self):
        console = Console(record=True, width=100)
        ui = UI(console=console)

        ui.show_done()

        output = console.export_text()
        self.assertIn("Context:", output)
        self.assertIn("Usage:", output)
        self.assertIn("Cost so far:", output)

    def test_max_steps_screen_displays_footer(self):
        console = Console(record=True, width=100)
        ui = UI(console=console)

        ui.show_max_steps()

        self.assertIn("Context:", console.export_text())

    def test_done_screen_displays_passed_metrics(self):
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

    def test_context_usage_shows_percentage_when_limit_is_known(self):
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
