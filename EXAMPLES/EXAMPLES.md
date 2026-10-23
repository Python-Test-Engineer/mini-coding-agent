# Hook and sandbox examples

The complete offline demonstrations are in `src/examplesCH02.py`. They do not
call the model API. Rich styles the hook messages, pass results, and expected
rejections, and puts the successful command output in a panel. Run both from
the `src/` directory:

```powershell
cd src
uv run python examplesCH02.py
```

The sandbox demo copies `src/examplesCH02.py` and a greeting script into the
repository's `work/` directory, where they remain after the program exits. It
also attempts to write `goodbye.py` in the repository root; the expected error
shows that the workspace blocks that path. The code snippets below can also be
copied separately if you want to explore one example at a time.

## 1. See lifecycle hooks run

A hook is a method the harness calls at a particular point in an agent turn.
This offline example calls a few hooks directly so you can see their arguments
and order without making a model request. In a real turn, the agent loop calls
these methods around input handling, tool execution, and errors.

Save this as `src/hooks_demo.py`:

```python
from types import SimpleNamespace

from lifecycle import Hooks


class StudentHooks(Hooks):
    """Print a short message when selected lifecycle events occur."""

    def before_input(self, agent, user_input):
        print(f"[hook] starting request: {user_input!r}")

    def before_tool_execute(self, agent, tool_name, arguments):
        print(f"[hook] about to call {tool_name} with {arguments}")

    def after_tool_execute(self, agent, tool_name, result):
        print(f"[hook] {tool_name} returned: {result}")

    def on_error(self, agent, error, phase):
        print(f"[hook] caught {type(error).__name__} during {phase}: {error}")

    def after_input(self, agent, user_input, output):
        print(f"[hook] request finished: {output!r}")


# The harness passes a context object as the first argument to each hook.
# This small stand-in provides the fields hooks commonly inspect.
context = SimpleNamespace(request="make a greeting", step=1, metrics={})
hooks = StudentHooks()

hooks.before_input(context, context.request)
hooks.before_tool_execute(context, "write_file", {"path": "hello.py"})
hooks.after_tool_execute(context, "write_file", "Created hello.py")
hooks.on_error(context, PermissionError("example rejection"), "tool_execute")
hooks.after_input(context, context.request, "Finished")
```

The output shows that a hook receives useful context plus the event-specific
values. `on_error` is called for an error the host catches; the example passes
it an error directly to keep the demonstration offline.

To use the same class with a real agent turn, keep the class in a module named
`student_hooks.py` under `src/`, then run this from `src/` after configuring
the project's OpenRouter API key:

```python
from agent import agent_loop
from student_hooks import StudentHooks

agent_loop("Write hello.py and run it", lifecycle_hooks=StudentHooks())
```

The real turn sends a model request and may use the project `work/` directory.
`agent_loop` calls the turn hooks automatically; session start/stop hooks are
called by the interactive `agent.py` entry point.

## 2. Try allowed and rejected sandbox operations

The workspace permits writes beneath its `work/` and `logs/` roots. It rejects
write paths that escape those roots, including a write to `../goodbye.py` from
the `work/` directory. The local runner also permits only a small command
allowlist and rejects shell operators before starting a process.

The same operations run when you launch `src/examplesCH02.py`. This standalone
version of the sandbox portion can be saved as `src/sandbox_demo.py`:

```python
from pathlib import Path

from sandbox import (
    ConstrainedLocalRunner,
    SandboxCommandError,
    SandboxPathError,
    SandboxWorkspace,
)


project_root = Path(__file__).resolve().parents[1]
workspace = SandboxWorkspace(project_root / "work", project_root / "logs")
runner = ConstrainedLocalRunner(workspace)

# PASS: copy this file into work/ so it stays visible after the demo.
source = Path(__file__).read_text(encoding="utf-8")
print(workspace.write_file("sandbox_demo.py", source))
print("Saved copy:", workspace.resolve_read_path("sandbox_demo.py"))

# PASS: write and run a small script in work/.
print(workspace.write_file("hello.py", 'print("Hello from work/")\n'))
print(runner.run("python hello.py"))

# FAIL (as expected): this path points to goodbye.py in the repository root.
try:
    workspace.write_file("../goodbye.py", 'print("blocked")\n')
except SandboxPathError as error:
    print("Rejected root write:", error)

# FAIL (as expected): shell syntax is rejected before a process starts.
try:
    runner.run("python hello.py & whoami")
except SandboxCommandError as error:
    print("Rejected command:", error)

# FAIL (as expected): git is not in the local runner's command allowlist.
try:
    runner.run("git status")
except SandboxCommandError as error:
    print("Rejected program:", error)
```

You should see the greeting from the allowed Python command, then the saved
file's path and rejection messages. The failures are expected: the Python
exceptions are caught so the program can print why each request was blocked
and continue. `work/examples.py` and `work/hello.py` stay on disk; the rejected
write does not create a root-level `goodbye.py`.

## What this sandbox does and does not do

The path checks protect writes made through the harness's file tools, and the
runner applies a command allowlist, avoids a shell, limits runtime and bounds
output. This is a **constrained local runner**, not operating-system isolation:
its child process still runs with the current user's permissions. Use trusted
code for this workshop; use a container or VM before running untrusted code.
