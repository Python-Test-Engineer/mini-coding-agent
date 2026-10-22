"""Host-enforced workspace and command controls for the teaching agent.

This module deliberately calls its process runner *constrained*, rather than a
security sandbox.  It prevents path traversal and avoids a host shell, but a
process still runs with the current Windows user's permissions.  Use a
container or VM runner before accepting untrusted prompts.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from lifecycle import Hooks


class SandboxError(Exception):
    """Base class for errors the host turns into model-readable tool results."""


class SandboxPathError(SandboxError):
    """Raised when a requested file path is outside the dedicated workspace."""


class SandboxCommandError(SandboxError):
    """Raised when a command violates the constrained local-runner policy."""


class SandboxRunner(Protocol):
    """The narrow interface a future container or VM runner must provide."""

    def run(self, command: str) -> str:
        """Run a command according to the runner's own enforced policy."""


@dataclass
class SandboxEvent:
    """An append-only audit record for one sandbox lifecycle transition."""

    kind: str
    detail: str
    step: int | None = None
    timestamp: float = field(default_factory=time.monotonic)


class SandboxWorkspace:
    """Contain agent file operations beneath one explicitly chosen directory."""

    def __init__(self, root: Path) -> None:
        # Resolve once so subsequent containment checks compare absolute paths.
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.events: list[SandboxEvent] = []

    def record(self, kind: str, detail: str, step: int | None = None) -> None:
        """Keep a bounded-in-scope audit trail without mutating agent messages."""
        self.events.append(SandboxEvent(kind, detail, step))

    def resolve_path(self, requested_path: str) -> Path:
        """Return a safe workspace path or reject an absolute/traversing path."""
        candidate = Path(requested_path)
        # A drive-qualified path such as ``C:notes.txt`` is not absolute on
        # Windows, but it still must not be interpreted inside this workspace.
        if candidate.is_absolute() or candidate.drive:
            raise SandboxPathError("path must be relative to the sandbox workspace")

        # ``strict=False`` resolves ``..`` even when the requested file is new.
        resolved = (self.root / candidate).resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise SandboxPathError("path escapes the sandbox workspace") from error
        return resolved

    def write_file(self, requested_path: str, content: str) -> str:
        """Write UTF-8 text after proving its target remains in the workspace."""
        target = self.resolve_path(requested_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Created {requested_path}"

    def edit_file(self, requested_path: str, old: str, new: str) -> str:
        """Replace the first matching string in a contained UTF-8 text file."""
        target = self.resolve_path(requested_path)
        original = target.read_text(encoding="utf-8")
        updated = original.replace(old, new, 1)
        target.write_text(updated, encoding="utf-8")
        return f"Edited {requested_path}: {old!r} -> {new!r}"

    def read_file(self, requested_path: str) -> str:
        """Read UTF-8 text after proving its target remains in the workspace."""
        return self.resolve_path(requested_path).read_text(encoding="utf-8")


class ConstrainedLocalRunner:
    """Run a small allowlist without a shell, with timeout and output limits.

    This class is intentionally replaceable by a Docker/VM implementation with
    the same ``run`` method when the workshop has a real isolated runtime.
    """

    def __init__(
        self,
        workspace: SandboxWorkspace,
        *,
        allowed_commands: set[str] | None = None,
        timeout_seconds: float = 20,
        max_output_chars: int = 12_000,
    ) -> None:
        self.workspace = workspace
        self.allowed_commands = allowed_commands or {
            "python",
            "python.exe",
            "python3",
            "pytest",
            "pytest.exe",
        }
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    def _parse(self, command: str) -> list[str]:
        """Parse an argument list and reject tokens that need a shell."""
        if not command.strip():
            raise SandboxCommandError("command must not be empty")
        if any(character in command for character in "|&;><`\n\r"):
            raise SandboxCommandError("shell operators are not allowed")
        try:
            arguments = shlex.split(command, posix=False)
        except ValueError as error:
            raise SandboxCommandError(f"invalid command arguments: {error}") from error
        if not arguments:
            raise SandboxCommandError("command must not be empty")

        executable = Path(arguments[0]).name.lower()
        if executable not in self.allowed_commands:
            raise SandboxCommandError(
                f"command {arguments[0]!r} is not allowed by the local runner"
            )
        return arguments

    def _bounded_output(self, value: str) -> str:
        """Prevent one noisy command from filling the model context or terminal."""
        if len(value) <= self.max_output_chars:
            return value
        return value[: self.max_output_chars] + "\n[output truncated by local runner]"

    def run(self, command: str) -> str:
        """Run an approved command without a shell and return a bounded result."""
        arguments = self._parse(command)
        try:
            completed = subprocess.run(
                arguments,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self.workspace.root,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise SandboxCommandError(
                f"command timed out after {self.timeout_seconds:g} seconds"
            ) from error
        except OSError as error:
            raise SandboxCommandError(f"could not start command: {error}") from error

        stdout = self._bounded_output(completed.stdout)
        stderr = self._bounded_output(completed.stderr)
        parts = [f"Exit code: {completed.returncode}"]
        if stdout:
            parts.extend(("STDOUT:", stdout))
        if stderr:
            parts.extend(("STDERR:", stderr))
        return "\n".join(parts)


class SandboxAuditHooks(Hooks):
    """Default lifecycle observer that records sandbox-related transitions."""

    def on_session_start(self, agent: Any) -> None:
        agent.workspace.record("session_started", "constrained local runner started")

    def on_session_stop(self, agent: Any) -> None:
        agent.workspace.record("session_stopped", "constrained local runner stopped")

    def before_tool_execute(
        self, agent: Any, tool_name: str, arguments: dict[str, Any]
    ) -> None:
        agent.workspace.record(
            "tool_requested",
            f"{tool_name} with {len(arguments)} argument(s)",
            agent.step,
        )

    def after_tool_execute(self, agent: Any, tool_name: str, result: str) -> None:
        status = "failed" if result.startswith("ERROR:") else "complete"
        agent.workspace.record("tool_finished", f"{tool_name}: {status}", agent.step)

    def on_error(self, agent: Any, error: Exception, phase: str) -> None:
        agent.workspace.record("host_error", f"{phase}: {error}", agent.step)
