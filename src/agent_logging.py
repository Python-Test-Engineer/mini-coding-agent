"""Small JSONL event logger used by the constrained sandbox.

The workshop keeps logging in its own module so the sandbox can focus on path
and command policy while still exposing each session's events for inspection.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass
class SandboxEvent:
    """An append-only audit record for one sandbox lifecycle transition."""

    kind: str
    detail: str
    step: int | None = None
    # Monotonic time is useful for measuring order and elapsed time; unlike a
    # wall clock, it cannot jump when the computer's date/time is adjusted.
    timestamp: float = field(default_factory=time.monotonic)


class EventLog:
    """Collect session events and append each one to a JSONL file."""

    def __init__(self, root: Path) -> None:
        # Resolve once so later writes use a stable, absolute location even if
        # the process changes its current working directory.
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # A random suffix avoids collisions if two sessions start in the same
        # second and makes each session's audit trail a separate file.
        self.path = self.root / f"agent-{stamp}-{uuid4().hex[:8]}.jsonl"
        # Create the file at session setup, even before the first model event.
        self.path.touch(exist_ok=False)
        # Keep events in memory too, so the running agent can inspect its
        # current session without reopening and parsing the JSONL file.
        self.events: list[SandboxEvent] = []

    def record(self, kind: str, detail: str, step: int | None = None) -> SandboxEvent:
        """Create an event, retain it for this session, and persist it to disk.

        Every source of log events (lifecycle hooks, tool calls, and policy
        rejections) uses this method so the in-memory view and JSONL file stay
        in sync.
        """
        event = SandboxEvent(kind, detail, step)
        self.events.append(event)
        self.write(event)
        return event

    def write(self, event: SandboxEvent) -> None:
        """Append a portable JSONL audit record with no terminal formatting."""
        # JSON Lines keeps each event independently readable and easy to stream
        # into simple tools such as PowerShell, Python, or a log viewer.
        payload = {
            "event": event.kind,
            "detail": event.detail,
            "step": event.step,
            "monotonic_seconds": event.timestamp,
            # Store a human-readable UTC time as well as monotonic session time.
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload, sort_keys=True) + "\n")
