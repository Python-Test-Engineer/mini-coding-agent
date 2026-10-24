"""Host-enforced workspace and command controls for the teaching agent.

This module deliberately calls its process runner *constrained*, rather than a
security sandbox.  It prevents path traversal and avoids a host shell, but a
process still runs with the current Windows user's permissions.  Use a
container or VM runner before accepting untrusted prompts.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable, NoReturn, Protocol

from lifecycle import Hooks
from agent_logging import EventLog, SandboxEvent
from sounds import play_sound


# Keep policy failures distinct from ordinary Python errors. The agent loop can
# show a useful message for a missing file, but must stop immediately when the
# model attempts a write outside the approved folders.
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

    Detection lives in :meth:`SandboxWorkspace.resolve_write_path`, but the
    *rendering* belongs to the UI: this default banner asks ``ui.show_forbidden``
    for the two red lines, so every visible string and colour still comes from
    ``ui.py`` and ``ui.json``. A host that wants another presentation can pass
    its own callable to :class:`SandboxWorkspace` instead.

    A fresh UI is built here so the banner still appears on the current
    ``sys.stdout``, which keeps it capturable by tests and by any host that
    redirects its own output. Rich is used when it is available and plain text
    otherwise, so the message still appears if the workshop dependencies are
    missing.
    """
    try:
        # Imported lazily: the UI pulls in Rich, and this module must stay
        # importable for hosts that only want the path and command policy.
        from ui import UI
    except ImportError:  # pragma: no cover - Rich is a workshop dependency
        print(f"[FORBIDDEN] {detail}")
        print("[FORBIDDEN] writes are limited to work/ and logs/ - stopping the agent.")
    else:
        UI().show_forbidden(detail)
    # SANDBOX: play the audible alert beside the visible forbidden banner.
    play_forbidden_sound()


def play_forbidden_sound() -> None:
    """Play the sandbox policy alert WAV before continuing after a violation."""
    # SANDBOX: all policy rejection paths call this helper; sync playback keeps
    # the alert audible even when a forbidden write immediately exits the app.
    # The WAV path, its play flag, and the missing-file/device handling live in
    # sounds.json and sounds.py, so the alert can be silenced without code edits.
    play_sound("sandbox_forbidden")


class SandboxWorkspace:
    """Allow writes only in ``work/`` and ``logs/``, while permitting reads."""

    def __init__(
        self,
        root: Path,
        log_root: Path | None = None,
        banner: Callable[[str], None] | None = None,
    ) -> None:
        # ``root`` is the work/ directory: bare relative filenames resolve
        # here, and it is also the current directory for approved commands.
        self.root = root.resolve()
        self.log_root = (log_root or self.root.parent / "logs").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.log_root.mkdir(parents=True, exist_ok=True)
        self.event_log = EventLog(self.log_root)
        # Preserve the convenient workspace.events view while keeping the
        # source of events and their durable storage together in logging.py.
        self.events = self.event_log.events
        # Injecting the banner lets tests and other hosts capture the red
        # message instead of printing it; the default prints to the terminal.
        self.banner = banner or print_forbidden

    def record(self, kind: str, detail: str, step: int | None = None) -> None:
        """Keep a bounded-in-scope audit trail without mutating agent messages."""
        # Route every source of audit activity through the shared logger, which
        # keeps its in-memory event list and JSONL file synchronized.
        self.event_log.record(kind, detail, step)

    def _is_writable_path(self, candidate: Path) -> bool:
        """Return whether a resolved path is contained by either writable root."""
        # Check both approved roots explicitly: normal project files belong in
        # work/, while audit output belongs in logs/.
        return any(
            self._is_beneath(candidate, allowed_root)
            for allowed_root in (self.root, self.log_root)
        )

    @staticmethod
    def _is_beneath(candidate: Path, root: Path) -> bool:
        """Use Path's containment operation instead of unsafe string prefixes."""
        # A string prefix check would confuse sibling names such as work-old
        # with work. relative_to checks path components, not character prefixes.
        try:
            candidate.relative_to(root)
        except ValueError:
            return False
        return True

    def _forbid(self, requested_path: str, detail: str) -> NoReturn:
        """Record, announce, and refuse an outside write in one place."""
        # Centralizing refusal makes every rejected write auditable and gives
        # the caller the original model-supplied path for reporting.
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
        # Normalize user shortcuts before checking containment. For example,
        # ~/notes.txt or %USERPROFILE%\notes.txt must not become a harmless
        # looking filename underneath work/.
        expanded = os.path.expandvars(os.path.expanduser(str(requested_path).strip()))
        candidate = Path(expanded)

        if candidate.is_absolute():
            # Absolute paths are allowed only if they ultimately resolve inside
            # one of the two approved roots (checked below).
            resolved = candidate.resolve(strict=False)
        elif candidate.drive:
            # "C:file.txt" is drive-relative and has surprising Windows
            # semantics, so it is always an outside request.
            self._forbid(requested_path, rejection)
        elif candidate.parts and candidate.parts[0].lower() == "logs":
            # Treat work-relative spellings "logs/file" and "work/file" as
            # explicit references to the configured roots, even when the
            # workspace folder itself has a different name on disk.
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

        # Resolve symlinks and .. components before the final check. Checking
        # only the original spelling would allow an in-work path to escape.
        if not self._is_writable_path(resolved):
            self._forbid(requested_path, rejection)
        return resolved

    def resolve_path(self, requested_path: str) -> Path:
        """Compatibility alias for callers checking a write/edit target."""
        return self.resolve_write_path(requested_path)

    def resolve_read_path(self, requested_path: str) -> Path:
        """Resolve any readable path; relative paths remain relative to work/."""
        # Reads are intentionally more permissive than writes for this teaching
        # agent. This is a convenience boundary, not confidential-data isolation.
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
        # Always resolve and validate before creating parent folders. Otherwise
        # even a rejected target could leave directories outside the workspace.
        target = self.resolve_write_path(requested_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Created {requested_path}"

    def edit_file(self, requested_path: str, old: str, new: str) -> str:
        """Replace text only after proving its target is in work/logs."""
        # Replace just the first match so repeated text is not unexpectedly
        # changed in multiple places; write_file policy applies to edits too.
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
        # This is an allowlist: anything not named here is rejected before a
        # process is created. The set can be narrowed for a particular lesson.
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
        # Shell syntax is deliberately unavailable. Passing a list to
        # subprocess with shell=False avoids shell expansion and command chaining.
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

        # Compare the executable's basename so "python.exe" is recognized, but
        # never trust a supplied directory path to grant a different command.
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
        # Arguments such as a script filename are restricted to the workspace.
        # This is a path policy only; it does not make Python code safe to run.
        for argument in arguments[1:]:
            candidate = Path(argument)
            if candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
                self._reject_command("command paths must stay in work")
        return arguments

    def _bounded_output(self, value: str) -> str:
        """Prevent one noisy command from filling the model context or terminal."""
        # Truncate stdout and stderr independently so one stream cannot flood the
        # agent with an unbounded result.
        if len(value) <= self.max_output_chars:
            return value
        return value[: self.max_output_chars] + "\n[output truncated by local runner]"

    def run(self, command: str) -> str:
        """Run an approved command without a shell and return a bounded result."""
        # Validate first: subprocess should only see an already-parsed,
        # policy-approved argument vector.
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

        # Return the exit status even on failure. A nonzero status is a result
        # for the agent to reason about, not a host exception.
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
