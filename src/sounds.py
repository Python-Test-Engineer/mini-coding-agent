"""Audible alerts for the mini coding agent, loaded from ``sounds.json``.

``ui.json`` owns every visible string and colour; ``sounds.json`` does the same
job for sound. Each named effect records three things:

``sound_file``
    The WAV to play. Environment variables such as ``%WINDIR%`` are expanded,
    so the standard Windows media folder can be referenced without hard-coding
    a drive letter in Python.
``play``
    ``true`` plays the effect; ``false`` silences it without editing code.
``location``
    Where the effect is triggered in the source, kept for reference.

Playback is best-effort: a missing file, a non-Windows host, or an unavailable
audio device stays silent and never raises, so an alert can never stop a turn.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Resolve the default catalogue beside this module, not from the launch folder,
# so the sounds travel with the source the way ``ui.json`` does.
CONFIG_PATH = Path(__file__).with_name("sounds.json")


def load_sounds(config_path: Path | None = None) -> dict[str, Any]:
    """Return the sound catalogue keyed by effect name."""
    path = config_path or CONFIG_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_sound_path(entry: dict[str, Any]) -> Path:
    """Turn an entry's ``sound_file`` into a concrete path, expanding %VARS%."""
    # expandvars also handles ``$VAR`` and ``~`` on other platforms, so a
    # future sound can be pointed at a user-writable location too.
    return Path(os.path.expandvars(entry.get("sound_file", "")))


def play_sound(
    name: str,
    *,
    asynchronous: bool = False,
    config_path: Path | None = None,
) -> bool:
    """Play the named WAV and report whether it actually played.

    Returns ``False`` (silently) when the effect is disabled in ``sounds.json``,
    the WAV is missing, or the host has no ``winsound`` module or audio device.
    ``asynchronous`` mirrors ``winsound.SND_ASYNC`` so a session-start jingle
    never delays the first prompt; callers that need the alert heard even as
    the process exits (the sandbox rejection) leave it ``False`` for sync play.
    """
    try:
        entry = load_sounds(config_path).get(name)
    except (OSError, ValueError, AttributeError, KeyError):
        # A missing or malformed catalogue must not break the agent.
        return False
    if not entry or not entry.get("play"):
        return False

    sound_path = resolve_sound_path(entry)
    if not sound_path.is_file():
        return False

    try:
        import winsound
    except ImportError:
        # Non-Windows platforms have no winsound and stay silent.
        return False

    flags = winsound.SND_FILENAME | winsound.SND_NODEFAULT
    if asynchronous:
        flags |= winsound.SND_ASYNC
    try:
        winsound.PlaySound(str(sound_path), flags)
    except (OSError, RuntimeError):
        # Missing audio devices or inaccessible files must not stop a turn.
        return False
    return True
