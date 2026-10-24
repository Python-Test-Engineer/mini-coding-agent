"""Verify the host enforces the constrained local sandbox policy."""

import contextlib
import io
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
    SandboxForbiddenError,
    SandboxPathError,
    SandboxWorkspace,
)
from lifecycle import Hooks
from ui import UI


class SandboxWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        # Capture the red banner so each test can assert on it without writing
        # to the real terminal.
        self.banners: list[str] = []
        self.workspace = SandboxWorkspace(
            Path(self.temp_dir.name) / "workspace", banner=self.banners.append
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_009_writes_and_reads_nested_relative_paths(self):
        self.workspace.write_file("nested/hello.txt", "hello")

        self.assertEqual(self.workspace.read_file("nested/hello.txt"), "hello")
        self.assertTrue((self.workspace.root / "nested" / "hello.txt").is_file())

    def test_010_rejects_parent_traversal(self):
        with self.assertRaisesRegex(SandboxPathError, "work or logs"):
            self.workspace.write_file("../outside.txt", "blocked")

    def test_011_rejects_write_and_edit_outside_work_or_logs(self):
        outside = Path(self.temp_dir.name) / "outside.txt"
        outside.write_text("original", encoding="utf-8")

        with self.assertRaisesRegex(SandboxPathError, "work or logs"):
            self.workspace.write_file(str(outside), "blocked")
        with self.assertRaisesRegex(SandboxPathError, "work or logs"):
            self.workspace.edit_file(str(outside), "original", "blocked")

        self.assertEqual(outside.read_text(encoding="utf-8"), "original")
        self.assertFalse(hasattr(self.workspace, "delete_file"))

    def test_012_allows_logs_and_an_explicit_external_read(self):
        self.workspace.write_file("logs/agent-note.txt", "event note")
        outside = Path(self.temp_dir.name) / "readable.txt"
        outside.write_text("read only", encoding="utf-8")

        self.assertEqual(
            (self.workspace.log_root / "agent-note.txt").read_text(encoding="utf-8"),
            "event note",
        )
        self.assertEqual(self.workspace.read_file(str(outside)), "read only")

    def test_024_rejects_home_and_system_relative_paths(self):
        """A "Desktop/..." or "~/..." request is an escape, not a work filename."""
        outside_requests = [
            "~/Desktop/notes.txt",
            "%USERPROFILE%/Desktop/notes.txt",
            "$HOME/notes.txt",
            "Users/me/notes.txt",
            "Desktop/notes.txt",
            "Documents/plan.md",
            "Downloads/report.csv",
        ]

        for request in outside_requests:
            with self.subTest(request=request):
                self.banners.clear()
                with self.assertRaises(SandboxForbiddenError) as rejected:
                    self.workspace.write_file(request, "blocked")

                # The exact request is kept for the caller and the banner fired.
                self.assertEqual(rejected.exception.requested_path, request)
                self.assertIn("write/edit path must stay in work or logs", self.banners[0])
                # Nothing was quietly created under work/.
                for name in ("~", "Users", "Desktop", "Documents", "Downloads", "$HOME"):
                    self.assertFalse((self.workspace.root / name).exists(), name)

    def test_025_forbidden_write_is_announced_and_audited(self):
        """Without an injected banner, the default printer writes the red lines."""
        # A workspace with no banner argument uses sandbox.print_forbidden().
        default_workspace = SandboxWorkspace(Path(self.temp_dir.name) / "default")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            with self.assertRaises(SandboxForbiddenError):
                default_workspace.write_file("../outside.txt", "blocked")

        printed = buffer.getvalue()
        self.assertIn("[FORBIDDEN]", printed)
        self.assertIn("stopping the agent", printed)
        self.assertEqual(printed.count("[FORBIDDEN]"), 2)

        events = default_workspace.event_log.path.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any('"event": "write_forbidden"' in line for line in events))

    def test_013_record_writes_jsonl_events_under_logs(self):
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

    def test_014_rejects_shell_operators_before_starting_a_process(self):
        with patch("sandbox.subprocess.run") as run_process:
            with self.assertRaisesRegex(SandboxCommandError, "shell operators"):
                self.runner.run("python script.py; whoami")

        run_process.assert_not_called()

    def test_015_rejects_commands_outside_the_allowlist(self):
        with self.assertRaisesRegex(SandboxCommandError, "not allowed"):
            self.runner.run("git status")

    def test_016_rejects_parent_paths_and_inline_python(self):
        with self.assertRaisesRegex(SandboxCommandError, "paths must stay"):
            self.runner.run("python ../outside.py")
        with self.assertRaisesRegex(SandboxCommandError, "inline Python"):
            self.runner.run('python -c "print(1)"')

    def test_017_uses_no_shell_and_bounds_output(self):
        completed = subprocess.CompletedProcess(
            ["python", "script.py"], 0, stdout="123456789", stderr="error text"
        )
        with patch("sandbox.subprocess.run", return_value=completed) as run_process:
            result = self.runner.run("python script.py")

        self.assertIn("Exit code: 0", result)
        self.assertIn("[output truncated by local runner]", result)
        self.assertEqual(run_process.call_args.kwargs["shell"], False)
        self.assertEqual(run_process.call_args.kwargs["cwd"], self.workspace.root)

    def test_018_turns_a_timeout_into_a_policy_error(self):
        with patch(
            "sandbox.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["python"], 0.1),
        ):
            with self.assertRaisesRegex(SandboxCommandError, "timed out"):
                self.runner.run("python script.py")


class SandboxAuditHookTests(unittest.TestCase):
    def test_019_records_tool_request_result_and_host_error(self):
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
    def test_020_agent_successfully_writes_to_an_allowed_workspace_path(self):
        console = Console(record=True, width=120)
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
                                        {
                                            "path": "work/notes/hello.txt",
                                            "content": "saved in the workspace",
                                        }
                                    ),
                                },
                            }
                        ],
                    }
                }
            ]
        }
        final_reply = {"choices": [{"message": {"content": "Finished", "tool_calls": []}}]}

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = SandboxWorkspace(Path(temp_dir) / "workspace")
            with patch("agent.ui", UI(console=console)), patch.object(
                agent, "WORKSPACE", workspace
            ), patch("agent.chat", side_effect=[tool_reply, final_reply]):
                agent.agent_loop("write a note in the workspace")

            written_file = workspace.root / "notes" / "hello.txt"
            self.assertEqual(
                written_file.read_text(encoding="utf-8"), "saved in the workspace"
            )
            self.assertIn("Created work/notes/hello.txt", console.export_text())

    def test_021_path_rejection_prints_forbidden_and_stops_the_run(self):
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
        # The reply after a blocked write must never be requested.
        final_reply = {"choices": [{"message": {"content": "Finished", "tool_calls": []}}]}

        banner = io.StringIO()
        with patch("agent.ui", UI(console=console)), patch(
            "agent.chat", side_effect=[tool_reply, final_reply]
        ) as chat, self.assertRaises(SystemExit) as exit_info:
            # resolve_write_path() prints its red banner straight to stdout.
            with contextlib.redirect_stdout(banner):
                agent.agent_loop("try an unsafe path")

        output = console.export_text()
        self.assertIn("path rejected", output)
        self.assertIn("write/edit path must stay in work or logs", output)
        # The red banner appears twice: the reason, then the policy.
        self.assertEqual(banner.getvalue().count("[FORBIDDEN]"), 2)
        self.assertIn("stopping the agent", banner.getvalue())
        # The turn ended immediately instead of asking the model to continue.
        self.assertNotIn("Finished", output)
        self.assertEqual(chat.call_count, 1)
        # A non-zero status makes a blocked write a script/CI failure.
        self.assertEqual(exit_info.exception.code, agent.FORBIDDEN_EXIT_CODE)

    def test_023_forbidden_write_ends_the_interactive_session(self):
        """The whole process exits instead of prompting for another request."""
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
                                        {
                                            "path": str(protected_file),
                                            "content": "blocked",
                                        }
                                    ),
                                },
                            }
                        ],
                    }
                }
            ]
        }
        later_reply = {"choices": [{"message": {"content": "should never run"}}]}
        banner = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = SandboxWorkspace(Path(temp_dir) / "workspace")
            with patch("agent.ui", UI(console=console)), patch.object(
                agent, "WORKSPACE", workspace
            ), patch.object(agent, "hooks", Hooks()), patch.object(
                sys, "argv", ["agent.py", "overwrite the readme"]
            ), patch(
                "agent.chat", side_effect=[tool_reply, later_reply]
            ) as chat, self.assertRaises(SystemExit) as exit_info:
                with contextlib.redirect_stdout(banner):
                    agent.main()

        output = console.export_text()
        self.assertEqual(exit_info.exception.code, agent.FORBIDDEN_EXIT_CODE)
        self.assertEqual(chat.call_count, 1)
        self.assertIn("[FORBIDDEN]", banner.getvalue())
        self.assertNotIn("should never run", output)
        # Rejection happens before any write, so the protected file is intact.
        self.assertEqual(protected_file.read_text(encoding="utf-8"), original)

    def test_022_agent_blocks_external_write_edit_and_delete_requests(self):
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

        banner = io.StringIO()
        with patch("agent.ui", UI(console=console)), patch(
            "agent.chat", side_effect=[tool_reply, final_reply]
        ) as chat, self.assertRaises(SystemExit) as exit_info:
            with contextlib.redirect_stdout(banner):
                agent.agent_loop("try external file operations")

        output = console.export_text()
        self.assertEqual(protected_file.read_text(encoding="utf-8"), original)
        # The first forbidden write stops the run, so the edit and delete calls
        # queued behind it are never executed or even reported.
        self.assertIn("write/edit path must stay in work or logs", banner.getvalue())
        self.assertNotIn("delete_file", output)
        self.assertNotIn("Finished", output)
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(exit_info.exception.code, agent.FORBIDDEN_EXIT_CODE)


if __name__ == "__main__":
    unittest.main()
