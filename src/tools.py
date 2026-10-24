"""The four host tools the model is allowed to ask for.

The model never touches the filesystem or a process itself. It only returns a
tool *name* plus JSON arguments, and ``agent.py`` looks that name up in the map
built by :func:`bind_tools` below. That name is the seam where the host keeps
control of the agent's behaviour.

Each function here is a thin, one-line wrapper around the enforcing object in
``sandbox.py``:

* :class:`~sandbox.SandboxWorkspace` decides where a file path may point;
* :class:`~sandbox.ConstrainedLocalRunner` decides which command may start.

Nothing in this module contains policy of its own - it exists so the loop reads
as ``result = tools[name](**args)`` without the sandbox details inline. The
matching model-visible descriptions live in ``brain.TOOL_SCHEMAS`` and must use
the same names.
"""

from __future__ import annotations

from functools import partial
from typing import Callable

from sandbox import ConstrainedLocalRunner, SandboxWorkspace


# --------------------------------------------------------------------------
# THE TOOL FUNCTIONS
# --------------------------------------------------------------------------
# The workspace or runner is the *first* parameter and is supplied by
# ``bind_tools()``. The model only ever supplies the arguments described in the
# tool schema, so its JSON keys line up with the remaining parameters.
def write_file(workspace: SandboxWorkspace, path: str, content: str) -> str:
    """Create UTF-8 text only under work/ or logs/."""
    return workspace.write_file(path, content)


def edit_file(workspace: SandboxWorkspace, path: str, old: str, new: str) -> str:
    """Edit UTF-8 text only under work/ or logs/."""
    return workspace.edit_file(path, old, new)


def read_file(workspace: SandboxWorkspace, path: str) -> str:
    """Read a work-relative file or any readable file at an absolute path."""
    return workspace.read_file(path)


def run(runner: ConstrainedLocalRunner, command: str) -> str:
    """Run an allowlisted command without using a host shell.

    This is a constrained local runner, not a strong OS-level sandbox. A future
    container or VM runner can implement the same interface for untrusted code.
    """
    return runner.run(command)


# --------------------------------------------------------------------------
# THE REGISTRY THE LOOP USES
# --------------------------------------------------------------------------
def bind_tools(
    workspace: SandboxWorkspace,
    runner: ConstrainedLocalRunner,
) -> dict[str, Callable[..., str]]:
    """Return the tool map with the host objects already attached.

    ``functools.partial`` pre-fills the first parameter of each function, so
    the bound callables accept exactly the arguments the model sends, for
    example ``write_file(path=..., content=...)``.

    The map is built from the workspace the loop is actually using, which is
    why ``agent_loop()`` calls this once per turn instead of at import time:
    the map and the enforcing objects can never drift apart.
    """
    return {
        # File tools all enforce through the same workspace object.
        "write_file": partial(write_file, workspace),
        "edit_file": partial(edit_file, workspace),
        "read_file": partial(read_file, workspace),
        # The command tool enforces through the runner instead.
        "run": partial(run, runner),
    }
