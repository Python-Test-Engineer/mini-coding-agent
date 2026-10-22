"""Verify the host enforces the constrained local sandbox policy."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agent
from sandbox import (
    ConstrainedLocalRunner,
    SandboxAuditHooks,
    SandboxCommandError,
    SandboxPathError,
    SandboxWorkspace,
)
from ui import UI


class SandboxWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = SandboxWorkspace(Path(self.temp_dir.name) / "workspace")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_writes_and_reads_nested_relative_paths(self):
        self.workspace.write_file("nested/hello.txt", "hello")

        self.assertEqual(self.workspace.read_file("nested/hello.txt"), "hello")
        self.assertTrue((self.workspace.root / "nested" / "hello.txt").is_file())

    def test_rejects_parent_traversal(self):
        with self.assertRaisesRegex(SandboxPathError, "work or logs"):
            self.workspace.write_file("../outside.txt", "blocked")

    def test_rejects_write_and_edit_outside_work_or_logs(self):
        outside = Path(self.temp_dir.name) / "outside.txt"
        outside.write_text("original", encoding="utf-8")

        with self.assertRaisesRegex(SandboxPathError, "work or logs"):
            self.workspace.write_file(str(outside), "blocked")
        with self.assertRaisesRegex(SandboxPathError, "work or logs"):
            self.workspace.edit_file(str(outside), "original", "blocked")

        self.assertEqual(outside.read_text(encoding="utf-8"), "original")
        self.assertFalse(hasattr(self.workspace, "delete_file"))

    def test_allows_logs_and_an_explicit_external_read(self):
        self.workspace.write_file("logs/agent-note.txt", "event note")
        outside = Path(self.temp_dir.name) / "readable.txt"
        outside.write_text("read only", encoding="utf-8")

        self.assertEqual(
            (self.workspace.log_root / "agent-note.txt").read_text(encoding="utf-8"),
            "event note",
        )
        self.assertEqual(self.workspace.read_file(str(outside)), "read only")

    def test_record_writes_jsonl_events_under_logs(self):
        self.workspace.record("lifecycle.before_loop", "waiting", step=1)

        lines = self.workspace.event_log.path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["event"], "lifecycle.before_loop")
        self.assertEqual(self.workspace.event_log.path.parent, self.workspace.log_root)


class ConstrainedLocalRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = SandboxWorkspace(Path(self.temp_dir.name) / "workspace")
        self.runner = ConstrainedLocalRunner(
            self.workspace,
            allowed_commands={"python"},
            timeout_seconds=0.1,
            max_output_chars=8,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rejects_shell_operators_before_starting_a_process(self):
        with patch("sandbox.subprocess.run") as run_process:
            with self.assertRaisesRegex(SandboxCommandError, "shell operators"):
                self.runner.run("python script.py; whoami")

        run_process.assert_not_called()

    def test_rejects_commands_outside_the_allowlist(self):
        with self.assertRaisesRegex(SandboxCommandError, "not allowed"):
            self.runner.run("git status")

    def test_rejects_parent_paths_and_inline_python(self):
        with self.assertRaisesRegex(SandboxCommandError, "paths must stay"):
            self.runner.run("python ../outside.py")
        with self.assertRaisesRegex(SandboxCommandError, "inline Python"):
            self.runner.run('python -c "print(1)"')

    def test_uses_no_shell_and_bounds_output(self):
        completed = subprocess.CompletedProcess(
            ["python", "script.py"], 0, stdout="123456789", stderr="error text"
        )
        with patch("sandbox.subprocess.run", return_value=completed) as run_process:
            result = self.runner.run("python script.py")

        self.assertIn("Exit code: 0", result)
        self.assertIn("[output truncated by local runner]", result)
        self.assertEqual(run_process.call_args.kwargs["shell"], False)
        self.assertEqual(run_process.call_args.kwargs["cwd"], self.workspace.root)

    def test_turns_a_timeout_into_a_policy_error(self):
        with patch(
            "sandbox.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["python"], 0.1),
        ):
            with self.assertRaisesRegex(SandboxCommandError, "timed out"):
                self.runner.run("python script.py")


class SandboxAuditHookTests(unittest.TestCase):
    def test_records_tool_request_result_and_host_error(self):
        workspace = SimpleNamespace(events=[], record=lambda *args: workspace.events.append(args))
        context = SimpleNamespace(workspace=workspace, step=3)
        hooks = SandboxAuditHooks()

        hooks.before_tool_execute(context, "read_file", {"path": "hello.py"})
        hooks.after_tool_execute(context, "read_file", "ERROR: missing file")
        hooks.on_error(context, ValueError("missing file"), "tool_execute")

        self.assertEqual(workspace.events[0], ("tool_requested", "read_file with 1 argument(s)", 3))
        self.assertEqual(workspace.events[1], ("tool_finished", "read_file: failed", 3))
        self.assertEqual(workspace.events[2], ("host_error", "tool_execute: missing file", 3))


class SandboxAgentIntegrationTests(unittest.TestCase):
    def test_path_rejection_is_returned_to_the_model_and_shown_by_the_ui(self):
        console = Console(record=True, width=120)
        tool_reply = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_path",
                                "function": {
                                    "name": "write_file",
                                    "arguments": '{"path": "../outside.txt", "content": "blocked"}',
                                },
                            }
                        ],
                    }
                }
            ]
        }
        final_reply = {"choices": [{"message": {"content": "Finished", "tool_calls": []}}]}

        with patch("agent.ui", UI(console=console)), patch(
            "agent.chat", side_effect=[tool_reply, final_reply]
        ):
            agent.agent_loop("try an unsafe path")

        output = console.export_text()
        self.assertIn("path rejected", output)
        self.assertIn("write/edit path must stay in work or logs", output)
        self.assertIn("Finished", output)

    def test_agent_blocks_external_write_edit_and_delete_requests(self):
        console = Console(record=True, width=120)
        protected_file = Path(agent.ROOT_DIR) / "README.md"
        original = protected_file.read_text(encoding="utf-8")
        tool_reply = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_write",
                                "function": {
                                    "name": "write_file",
                                    "arguments": json.dumps(
                                        {"path": str(protected_file), "content": "blocked"}
                                    ),
                                },
                            },
                            {
                                "id": "call_edit",
                                "function": {
                                    "name": "edit_file",
                                    "arguments": json.dumps(
                                        {
                                            "path": str(protected_file),
                                            "old": "mini-coding-agent",
                                            "new": "blocked",
                                        }
                                    ),
                                },
                            },
                            {
                                "id": "call_delete",
                                "function": {
                                    "name": "delete_file",
                                    "arguments": json.dumps({"path": str(protected_file)}),
                                },
                            },
                        ],
                    }
                }
            ]
        }
        final_reply = {"choices": [{"message": {"content": "Finished", "tool_calls": []}}]}

        with patch("agent.ui", UI(console=console)), patch(
            "agent.chat", side_effect=[tool_reply, final_reply]
        ):
            agent.agent_loop("try external file operations")

        output = console.export_text()
        self.assertEqual(protected_file.read_text(encoding="utf-8"), original)
        self.assertGreaterEqual(output.count("write/edit path must stay in work or logs"), 2)
        self.assertIn("delete_file", output)
        self.assertIn("Finished", output)


if __name__ == "__main__":
    unittest.main()
