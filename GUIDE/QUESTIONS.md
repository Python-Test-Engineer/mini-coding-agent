<!-- This will have questions regarding hwo things work and their answers. -->

# CH01

1.1 

## CH02

### 2.1 How do I modify or add a hook?

Create a class that inherits from `Hooks` in `src/lifecycle.py`, then override
only the callback methods you need. For example:

```python
from lifecycle import Hooks


class ToolCounter(Hooks):
    def __init__(self):
        self.count = 0

    def after_tool_execute(self, agent, tool_name, result):
        if not result.startswith("ERROR:"):
            self.count += 1
```

When calling the agent from Python, pass an instance with
`agent_loop("your request", lifecycle_hooks=ToolCounter())`. If you want a
different default for the command-line app, change the `hooks` instance near
the top of `src/agent.py`. Keep the callback name and parameters aligned with
the methods in `Hooks`.

### 2.2 What does the `agent` argument passed to a hook contain?

It is an `AgentContext` made by `agent_loop()` for the current request. It
provides the request text, live conversation `messages`, shared usage `metrics`,
the UI, the sandbox workspace, and the current model step. Hooks can inspect
these values or keep their own state, as `ToolCounter` does above. The context
is for observing the agent; the host still decides which tools run and what
goes back to the model.

### 2.3 In what order do the hooks run?

For each request, the agent calls `before_input` and `before_loop`. Each model
step calls `before_brain_request`, then `after_brain_response`. If the model
requests tools, each tool has `before_tool_execute` and `after_tool_execute`
callbacks. When the request finishes, `after_loop` and `after_input` run. The
interactive `main()` function separately calls `on_session_start` and
`on_session_stop` around the whole conversation.

### 2.4 How does a model tool call become a Python function call?

`TOOL_SCHEMAS` in `src/brain.py` describes the available tools to the model.
The model returns a tool name and JSON arguments; the agent parses those
arguments, looks the name up in the tool map that `tools.bind_tools()` built for
this turn, and calls that Python function. The schema tells the model what it
may request, while the bound tool functions decide what the host can actually
execute.

### 2.5 What happens if a tool or hook raises an exception?

If a tool fails, the agent reports the error to `on_error`, turns it into an
`ERROR: ...` result, and sends that result back to the model. The
`after_tool_execute` hook still runs, so it can record the failed outcome. If a
lifecycle hook itself raises an exception, `_call_hook()` displays a hook-error
panel and lets the agent loop continue. This prevents optional extension code
from stopping the host loop.

### 2.6 Where can the agent read and write files?

`SandboxWorkspace` in `src/sandbox.py` resolves paths before file operations.
Writes and edits are allowed only beneath the repository's `work/` or `logs/`
directories; a bare relative path such as `hello.py` means `work/hello.py`.
Reads use `work/` for relative paths, but an explicit absolute path can read
any file the current user can access. The tool registry does not provide a
delete operation.

### 2.7 Is `ConstrainedLocalRunner` a secure sandbox?

No. It is a constrained local runner for this workshop. It rejects shell
operators, allows only Python and pytest command names, blocks inline `-c`
commands and out-of-work paths, runs without a shell from `work/`, limits a
command to 20 seconds, and truncates captured output. On Windows, a sandbox
policy rejection plays `C:\Windows\Media\tada.wav`; that path and its `play` flag
are declared in `src/sounds.json` and played through `src/sounds.py`. The process still runs with
the current user's operating-system permissions and has no network isolation.
Use a container or VM before running untrusted code.

### 2.8 Where are lifecycle events recorded?

`SandboxWorkspace.record()` keeps events in memory and appends them as JSON
lines to a uniquely named file under `logs/`. The `EventLog` writes structured
fields such as the event name, detail, model step, monotonic time, and UTC
timestamp. `SandboxAuditHooks` records session, tool, and caught-error events;
the agent also records lifecycle transitions.

### 2.9 How do I change the lifecycle messages and colours in the terminal?

Edit the `labels.lifecycle_events` and `styles.lifecycle_events` maps in
`src/ui.json`. `UI.show_lifecycle_event()` in `src/ui.py` reads those values
when it renders each trace line, so you can change wording and Rich styles
without changing the agent loop. Unknown event names get a readable fallback.

### 2.10 What does `lifecycle_hooks=` change in an interactive run?

Passing `lifecycle_hooks=` to `agent_loop()` replaces the hook instance for
that request's turn callbacks. The command-line `main()` currently uses the
module-level `hooks` instance for the session-start and session-stop callbacks.
If you build your own session runner and need custom session callbacks, call
those callbacks around your conversation as `main()` does.
