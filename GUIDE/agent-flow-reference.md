# Logging, hooks, sandbox, and UI: agent flow reference

This guide explains how the Chapter 02 agent moves a request through its host
loop, lifecycle hooks, sandbox checks, event log, and terminal UI. It follows
the implementation in `src/agent.py`, `src/lifecycle.py`, `src/sandbox.py`,
`src/ui.py`, and `src/ui.json`.

The final section turns those relationships into a scene outline for a future
HTML animation. Each scene can become a highlighted component, an animated
event, and a short explanation.

## The four responsibilities

| Part | Main files | Responsibility |
| --- | --- | --- |
| Agent host | `src/agent.py` | Owns the request loop, calls the model, selects tools, catches errors, and calls UI methods. |
| Lifecycle hooks | `src/lifecycle.py`, `src/sandbox.py` | Observe session and turn transitions. `SandboxAuditHooks` adds audit entries. |
| Sandbox policy | `src/sandbox.py` | Checks file paths and command arguments where host operations run. |
| Terminal UI | `src/ui.py`, `src/ui.json` | Formats lifecycle traces, sandbox statuses, tool calls, results, and errors. |

The agent is the coordinator. Hooks observe its transitions, the sandbox checks
the operations, and the UI renders information the host sends to it.

## A session contains one or more turns

The command-line `main()` function wraps the interactive conversation in
session callbacks:

```text
main()
  ├─ on_session_start
  ├─ agent_loop(...)  ← one call for each user request
  ├─ agent_loop(...)
  └─ on_session_stop
```

`on_session_start` plays the existing Windows logon WAV when available.
`SandboxAuditHooks` calls the base hook and records `session_started` in the
workspace event log. At the end of the conversation, it records
`session_stopped`; `main()` also asks the UI to render the stopped status.

Each `agent_loop()` call creates an `AgentContext`. Hooks receive this context
so they can inspect the current request, live messages, metrics, UI, workspace,
and current model step.

## One turn through the agent loop

The normal request path is:

```text
User request
    ↓
agent_loop: render request and runner status
    ↓
before_input → before_loop
    ↓
before_brain_request → chat(messages) → after_brain_response
    ↓
tool call? ── yes ──→ before_tool_execute → host tool → after_tool_execute
    │                                                    ↓
    │                                      append tool result to messages
    │                                                    └──→ next model step
    └── no tool call ──→ after_loop → after_input → render completion
```

At the beginning of a turn, the agent calls `ui.show_start()` and
`ui.show_sandbox_status("local_runner", ...)`, then invokes `before_input` and
`before_loop`.

Each model step invokes `before_brain_request`, calls `chat(messages)`, updates
usage metrics, and invokes `after_brain_response`. If the model returns a tool
call, the host displays it with `ui.show_tool()`. For `write_file`, it also
displays the proposed source with `ui.show_code()`.

The host then invokes `before_tool_execute`, runs the Python function in the
`TOOLS` registry, invokes `after_tool_execute`, displays the result with
`ui.show_result()`, and appends the tool result to the conversation. The next
model step can use that result. A final response with no tool calls ends the
loop and renders the completion footer.

## How an event reaches the UI and the log

The agent calls UI methods directly. There is no separate event queue or UI
event bus in this implementation.

For a regular lifecycle event, `_call_hook()` performs three actions in order:

1. Calls `workspace.record("lifecycle.<event>", detail, step)`.
2. Calls `context.ui.show_lifecycle_event(event, detail)`.
3. Invokes the matching callback on the configured `Hooks` instance.

The UI receives an event name and short detail. `UI.show_lifecycle_event()`
looks up the visible label and Rich style in `src/ui.json`, builds the trace
line, and prints it. The agent decides when the event occurred; `ui.py` and
`ui.json` decide how that event looks.

Sandbox statuses follow a related route. When the agent catches a
`SandboxPathError` or `SandboxCommandError`, `_report_error()` records
`lifecycle.error`, asks the UI to show the matching sandbox status, renders the
`on_error` lifecycle line, and then calls the error hook. Timeouts use the
`command_timed_out` status; other command-policy errors use `command_rejected`.

Other UI calls show the request, model text, tool call, code, tool result,
hook-error panel, and completion footer. This keeps terminal formatting out of
the loop and policy code.

## What the event log contains

`SandboxWorkspace.record()` keeps each event in the workspace's in-memory
`events` list and appends one JSON object to a uniquely named file under
`logs/`. Each JSONL row contains:

- event name and short detail;
- model step, when one applies;
- monotonic time and UTC recording time.

The default `SandboxAuditHooks` adds audit events for session start/stop, tool
requests, tool outcomes, and caught host errors. The agent also records each
lifecycle transition and each caught error. These records answer different
questions: lifecycle entries show when the host crossed a boundary, while audit
entries describe the requested action or outcome.

`_call_hook()` contains exceptions raised by optional hook callbacks. It records
`lifecycle.hook_error`, asks the UI to display a hook-error panel, and continues
the host loop. Tool errors still follow the tool-error path and are returned to
the model as `ERROR: ...` results, except for the fatal forbidden write/edit
case described below.

## Where the sandbox checks happen

File tools go through `SandboxWorkspace`:

| Operation | Rule |
| --- | --- |
| `write_file` and `edit_file` | Resolved targets must remain beneath repository-root `work/` or `logs/`. |
| Relative file reads | Resolve from `work/`; `logs/...` resolves beneath the log root. |
| Absolute file reads | Allowed for any file readable by the current user. |
| Delete | No delete tool is registered. |

The workspace expands home and environment variables before checking a write.
It resolves the final path so traversal and symlink escapes can be rejected.
A path that looks like a home or system location, such as `Desktop/file.txt`,
is treated as an outside write instead of a new `work/Desktop/` directory.

Commands go through `ConstrainedLocalRunner`. Before starting a process, it
rejects shell operators, commands outside the Python and pytest allowlist,
inline `-c` code, and command paths that are absolute, drive-qualified, or
traverse through `..`. It launches with `shell=False`, uses `work/` as the
working directory, applies a timeout, and bounds captured output.

These checks constrain operations made through the host tools. The runner's
child process still uses the current user's operating-system permissions and
has no network isolation. A container or VM with its own permissions and
filesystem boundary is needed to isolate executed code.

## What happens when a policy check rejects an operation

Every sandbox policy rejection plays `C:\Windows\Media\tada.wav` on Windows
when the file and audio device are available. Playback is synchronous. The
sound helper is called at the policy check, alongside the `[FORBIDDEN]` banner
for blocked writes and edits.

The paths then diverge by error type:

### Blocked write or edit

`SandboxWorkspace._forbid()` records `write_forbidden`, prints the red
`[FORBIDDEN]` banner, plays the alert, and raises `SandboxForbiddenError`.
The agent catches it, displays the path-rejected status and lifecycle error,
shows the failed tool result, and runs the turn-completion hooks. It then exits
with `FORBIDDEN_EXIT_CODE` (`2`), so the model cannot retry the write.

### Rejected command or drive-relative read

The command parser or read-path resolver plays the alert and raises a sandbox
error. The agent reports the error through the UI and returns an `ERROR: ...`
tool result to the model. The loop can continue with a corrected request.
Timeout and process-launch errors are operational failures; the policy-alert
sound is for rule rejections.

Hook callbacks provide observation and extension points. File and command
enforcement runs inside `SandboxWorkspace` and `ConstrainedLocalRunner`, at the
point the host is about to perform the operation.

## Animation-ready storyboard

Use three visual lanes in a future HTML animation:

1. **Host lane** — request, `agent_loop`, model call, requested tool, tool
   result, and next model step or completion.
2. **Policy lane** — `SandboxWorkspace` or `ConstrainedLocalRunner`, with an
   allowed path forward and a rejection branch.
3. **Observer lane** — `workspace.record()`, the direct UI method call, and
   the lifecycle or audit callback.

| Scene | Highlight | Visual event | Caption |
| --- | --- | --- | --- |
| 1. Session | `main()` and session hooks | A frame opens around multiple turns. | Session hooks wrap the interactive conversation. |
| 2. Turn begins | `agent_loop()` | The request enters; `before_input` and `before_loop` appear. | The host starts a request and announces its transitions. |
| 3. Model step | Model request and response | A message travels to the model and a tool call returns. | The host sends the conversation and receives the model's next action. |
| 4. Lifecycle event | `_call_hook()` → log → UI → hook | A small event token branches to JSONL and terminal output before reaching the callback. | The host records and renders the event, then invokes the observer. |
| 5. Policy check | Workspace or runner | A path or command passes through the policy gate. | The boundary checks the operation where it runs. |
| 6. Allowed tool | Tool result | The result returns to the host, then back to the model. | Tool results join the conversation before the next step. |
| 7. Rejected write | `_forbid()` | The path hits a red stop, JSONL gets `write_forbidden`, the banner and sound fire, and the agent exits after reporting the error. | A forbidden write is fatal and the model does not retry. |
| 8. Rejected command | `_reject_command()` | A command hits a stop, sounds the alert, then returns an error result through the UI. | A rejected command can be corrected on a later model step. |
| 9. Turn/session close | `after_loop`, `after_input`, `on_session_stop` | Turn frame closes; session frame closes after the conversation. | Turn hooks run for each request; session hooks run once around the conversation. |

### Suggested animation controls

- **Play/Pause** advances one scene at a time and holds the current explanation.
- **Next/Back** lets a reader inspect a scene without waiting for the timer.
- **Allowed/Blocked** switches between the successful tool cycle and rejection
  branch.
- **Reduced motion** presents the same scene changes without long transitions.

The [animated flow page](agent-flow.html) is a compact overview. Focused
animations trace [logging](logging-animation.html), [hooks](hooks-animation.html),
[sandbox checks](sandbox-animation.html), and [UI rendering](ui-animation.html)
one feature at a time.
