"""Host-enforced workspace and command controls for the teaching agent.

This module deliberately calls its process runner *constrained*, rather than a
security sandbox.  It prevents path traversal and avoids a host shell, but a
process still runs with the current Windows user's permissions.  Use a
container or VM runner before accepting untrusted prompts.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, NoReturn, Protocol
from uuid import uuid4

from lifecycle import Hooks


class SandboxError(Exception):
    """Base class for errors the host turns into model-readable tool results."""


class SandboxPathError(SandboxError):
    """Raised when a requested file path is outside the dedicated workspace."""


class SandboxForbiddenError(SandboxPathError):
    """Raised when a write/edit target is provably outside work/ and logs/.

    This is a policy violation, not a recoverable tool error: the host must
    stop its loop when it sees this type. ``requested_path`` keeps the exact
    string the model asked for so the caller can report or audit it.
    """

    def __init__(self, requested_path: str, detail: str) -> None:
        super().__init__(detail)
        self.requested_path = requested_path


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


class EventLog:
    """Write one JSON object per lifecycle event beneath the approved log root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = self.root / f"agent-{stamp}-{uuid4().hex[:8]}.jsonl"
        # Create the file at session setup, even before the first model event.
        self.path.touch(exist_ok=False)

    def write(self, event: SandboxEvent) -> None:
        """Append a portable JSONL audit record with no terminal formatting."""
        payload = {
            "event": event.kind,
            "detail": event.detail,
            "step": event.step,
            "monotonic_seconds": event.timestamp,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload, sort_keys=True) + "\n")


# Folder names a model uses when it means "somewhere outside work/". A relative
# path starting with one of these is not a filename in the workspace: it is a
# request for a real home or system folder, such as ``Desktop/notes.txt`` or
# ``Users/me/notes.txt``, which Windows treats as relative only because it has
# no drive letter. Without this check such a request was quietly created under
# work/ instead of being refused.
OUTSIDE_LOCATION_NAMES = frozenset(
    {
        "users",
        "windows",
        "program files",
        "program files (x86)",
        "programdata",
        "desktop",
        "documents",
        "downloads",
        "appdata",
        "onedrive",
        "library",
        "system32",
    }
)


def print_forbidden(detail: str) -> None:
    """Print the red FORBIDDEN banner at the point where it is detected.

    Detection lives in :meth:`SandboxWorkspace.resolve_write_path`, so the
    banner is printed there instead of in the agent loop. Rich is used when it
    is available and plain text otherwise, so the message still appears if the
    demo runs without the workshop dependencies.
    """
    try:
        from rich.console import Console
        from rich.text import Text
    except ImportError:  # pragma: no cover - Rich is a workshop dependency
        print(f"[FORBIDDEN] {detail}")
        print("[FORBIDDEN] writes are limited to work/ and logs/ - stopping the agent.")
    else:
        # A fresh console writes to the current sys.stdout, which keeps the banner
        # capturable by tests and by any host that redirects its own output.
        console = Console()
        console.print(Text(f"[FORBIDDEN] {detail}", style="bold red"))
        console.print(
            Text(
                "[FORBIDDEN] writes are limited to work/ and logs/ - stopping the agent.",
                style="bold red",
            )
        )
    # SANDBOX: play the audible alert beside the visible forbidden banner.
    play_forbidden_sound()


def play_forbidden_sound() -> None:
    """Play the sandbox policy alert WAV before continuing after a violation."""
    # SANDBOX: all policy rejection paths call this helper; sync playback keeps
    # the alert audible even when a forbidden write immediately exits the app.
    error_sound = Path(r"C:\Windows\Media\tada.wav")
    if not error_sound.is_file():
        return

    try:
        import winsound

        winsound.PlaySound(
            str(error_sound),
            winsound.SND_FILENAME | winsound.SND_NODEFAULT,
        )
    except (ImportError, OSError, RuntimeError):
        # Non-Windows platforms or unavailable audio devices are silent.
        pass


class SandboxWorkspace:
    """Allow writes only in ``work/`` and ``logs/``, while permitting reads."""

    def __init__(
        self,
        root: Path,
        log_root: Path | None = None,
        banner: Callable[[str], None] | None = None,
    ) -> None:
        # ``root`` remains the command runner's current directory: work/.
        self.root = root.resolve()
        self.log_root = (log_root or self.root.parent / "logs").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.log_root.mkdir(parents=True, exist_ok=True)
        self.events: list[SandboxEvent] = []
        self.event_log = EventLog(self.log_root)
        # Injecting the banner lets tests and other hosts capture the red
        # message instead of printing it; the default prints to the terminal.
        self.banner = banner or print_forbidden

    def record(self, kind: str, detail: str, step: int | None = None) -> None:
        """Keep a bounded-in-scope audit trail without mutating agent messages."""
        event = SandboxEvent(kind, detail, step)
        self.events.append(event)
        self.event_log.write(event)

    def _is_writable_path(self, candidate: Path) -> bool:
        """Return whether a resolved path is contained by either writable root."""
        return any(
            self._is_beneath(candidate, allowed_root)
            for allowed_root in (self.root, self.log_root)
        )

    @staticmethod
    def _is_beneath(candidate: Path, root: Path) -> bool:
        """Use Path's containment operation instead of unsafe string prefixes."""
        try:
            candidate.relative_to(root)
        except ValueError:
            return False
        return True

    def _forbid(self, requested_path: str, detail: str) -> NoReturn:
        """Record, announce, and refuse an outside write in one place."""
        self.record("write_forbidden", detail)
        # The red banner is printed here, where the policy decision is made, so
        # no caller can forget to report it.
        self.banner(detail)
        # Custom banners do not include the default printer's sound call.
        if self.banner is not print_forbidden:
            play_forbidden_sound()
        raise SandboxForbiddenError(requested_path, detail)

    @staticmethod
    def _looks_like_outside_location(candidate: Path) -> bool:
        """Detect a home- or system-relative path the model meant literally."""
        if not candidate.parts:
            return False
        first = candidate.parts[0].lower()
        # An unexpanded "~", "$HOME", or "%USERPROFILE%" is still an outside
        # request; treat it as one instead of creating a folder named "~".
        if first.startswith(("~", "$", "%")):
            return True
        return first in OUTSIDE_LOCATION_NAMES

    def resolve_write_path(self, requested_path: str) -> Path:
        """Return a work/log path, or refuse any write/edit target outside.

        Every outside request prints the red FORBIDDEN banner and raises
        :class:`SandboxForbiddenError`. Callers must stop their loop on that
        error: unlike a missing file, it is a policy violation that must not be
        retried with a different path.
        """
        rejection = (
            "write/edit path must stay in work or logs; "
            f"blocked requested path: {requested_path}"
        )
        # Expand "~" and environment variables first, so a home-relative request
        # cannot be mistaken for an ordinary filename inside work/.
        expanded = os.path.expandvars(os.path.expanduser(str(requested_path).strip()))
        candidate = Path(expanded)

        if candidate.is_absolute():
            resolved = candidate.resolve(strict=False)
        elif candidate.drive:
            # "C:file.txt" is drive-relative and has surprising Windows
            # semantics, so it is always an outside request.
            self._forbid(requested_path, rejection)
        elif candidate.parts and candidate.parts[0].lower() == "logs":
            resolved = (self.log_root / Path(*candidate.parts[1:])).resolve(strict=False)
        elif candidate.parts and candidate.parts[0].lower() == "work":
            resolved = (self.root / Path(*candidate.parts[1:])).resolve(strict=False)
        elif self._looks_like_outside_location(candidate):
            # "Desktop/notes.txt" and "Users/me/notes.txt" are outside requests
            # that only look relative; never turn them into work/ subfolders.
            self._forbid(requested_path, rejection)
        else:
            # Bare relative paths preserve the workshop's usual ``hello.py`` API.
            resolved = (self.root / candidate).resolve(strict=False)

        if not self._is_writable_path(resolved):
            self._forbid(requested_path, rejection)
        return resolved

    def resolve_path(self, requested_path: str) -> Path:
        """Compatibility alias for callers checking a write/edit target."""
        return self.resolve_write_path(requested_path)

    def resolve_read_path(self, requested_path: str) -> Path:
        """Resolve any readable path; relative paths remain relative to work/."""
        candidate = Path(requested_path)
        if candidate.is_absolute():
            return candidate.resolve(strict=False)
        if candidate.drive:
            # A drive-relative path has surprising Windows semantics, so require
            # an explicit absolute path for an outside-workspace read.
            play_forbidden_sound()
            raise SandboxPathError("use an absolute path to read another drive")
        if candidate.parts and candidate.parts[0].lower() == "logs":
            return (self.log_root / Path(*candidate.parts[1:])).resolve(strict=False)
        return (self.root / candidate).resolve(strict=False)

    def write_file(self, requested_path: str, content: str) -> str:
        """Write UTF-8 text only after proving its target is in work/logs."""
        target = self.resolve_write_path(requested_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Created {requested_path}"

    def edit_file(self, requested_path: str, old: str, new: str) -> str:
        """Replace text only after proving its target is in work/logs."""
        target = self.resolve_write_path(requested_path)
        original = target.read_text(encoding="utf-8")
        updated = original.replace(old, new, 1)
        target.write_text(updated, encoding="utf-8")
        return f"Edited {requested_path}: {old!r} -> {new!r}"

    def read_file(self, requested_path: str) -> str:
        """Read UTF-8 text from any readable absolute path or work-relative path."""
        return self.resolve_read_path(requested_path).read_text(encoding="utf-8")


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

    @staticmethod
    def _reject_command(detail: str) -> NoReturn:
        """Play the sandbox alert and reject a command that breaks policy."""
        play_forbidden_sound()
        raise SandboxCommandError(detail)

    def _parse(self, command: str) -> list[str]:
        """Parse an argument list and reject tokens that need a shell."""
        if not command.strip():
            self._reject_command("command must not be empty")
        if any(character in command for character in "|&;><`\n\r"):
            self._reject_command("shell operators are not allowed")
        try:
            arguments = shlex.split(command, posix=False)
        except ValueError as error:
            self._reject_command(f"invalid command arguments: {error}")
        if not arguments:
            self._reject_command("command must not be empty")

        executable = Path(arguments[0]).name.lower()
        if executable not in self.allowed_commands:
            self._reject_command(
                f"command {arguments[0]!r} is not allowed by the local runner"
            )
        # Do not let the command line point the interpreter or test runner at
        # a parent/absolute path. This constrains command *arguments*; a local
        # Python process still needs a container/VM for OS-level isolation.
        if "-c" in arguments:
            self._reject_command("inline Python commands are not allowed")
        for argument in arguments[1:]:
            candidate = Path(argument)
            if candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
                self._reject_command("command paths must stay in work")
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
        # Keep the base session-start jingle and add the audit record.
        super().on_session_start(agent)
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
