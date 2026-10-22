# Plan: use lifecycle hooks with a sandboxed tool host

## Goal

Replace the current demonstration-only tool execution path with a sandboxed
workspace for agent-created files and commands. The model should be able to
create, edit, read, and run code in a dedicated environment, while the Python
host retains the final authority over what executes.

Lifecycle hooks help make this work visible, auditable, and testable. They do
not create a security boundary by themselves. The security boundary must be
enforced by the code that resolves file paths and starts processes.

## Implementation status

The repository now implements the local, host-enforced stages of this plan:

- `SandboxWorkspace` allows write/edit operations only in `work/` and `logs/`.
- `EventLog` writes every lifecycle transition as JSONL beneath `logs/`.
- `ConstrainedLocalRunner` rejects shell operators and unapproved commands,
  uses `shell=False`, and applies timeout and output limits.
- `SandboxAuditHooks` records session, tool, and caught-error events.
- The UI renders sandbox status independently of sandbox policy code.

Docker and Podman are not installed in the current workshop environment, so
the container/VM phase remains intentionally unimplemented. The current runner
is documented as constrained local execution, never as an operating-system
security boundary.

## Current position

`src/agent.py` exposes four direct host tools:

- `write_file`, `edit_file`, and `read_file` build paths from `WORKDIR`.
- `run` calls `subprocess.run(..., shell=True, cwd=WORKDIR)` using the current
  user's permissions.

The `work/` directory is a convenient default location. It is not a sandbox:
paths can escape it and commands can access the host machine.

Chapter 02 added lifecycle callbacks around the loop and each tool execution:

```text
before_tool_execute -> host runs tool -> after_tool_execute
                         |
                         +-> on_error when the host catches an error
```

These are the useful hook boundaries for a sandbox, but no hook should be the
only code that permits or denies an action.

## Design principles

1. **Enforce next to the action.** The file/path resolver and process runner
   must reject unsafe work even if no hooks are installed or a hook fails.
2. **Use hooks for observation and policy decisions.** Hooks can log intent,
   record a decision, collect timing, and notify the UI. They should not need
   to manipulate the agent loop directly.
3. **Keep the tool schema stable where possible.** The model can continue to
   request `write_file`, `edit_file`, `read_file`, and `run`; the host changes
   where and how those operations happen.
4. **Make policy explicit and configurable.** Allowed commands, resource
   limits, and network access must be settings that the host reads and tests.
5. **Fail closed.** If sandbox setup, path validation, or a required approval
   check cannot complete, return an error result and do not run the command.

## Target shape

```text
model tool request
      |
      v
before_tool_execute hook  ---> audit event / optional approval request
      |
      v
ToolExecutor (host-enforced policy)
      |-- validate tool name and arguments
      |-- resolve a path beneath the sandbox workspace
      |-- start command in isolated runtime with limits
      v
sandbox workspace / process
      |
      v
after_tool_execute hook   ---> audit result / duration / UI trace
```

The `ToolExecutor` is the important part: it is the only route from a model
tool request to filesystem or process work. Hooks surround it and report on it.

## Phase 1: make the current host tools safe by construction

Create a small `SandboxWorkspace` class backed by repository-root `work/` and
`logs/` directories.

Its responsibilities are:

- Resolve a requested relative path with `Path.resolve()`.
- Reject absolute paths and any resolved target outside the workspace root.
- Create parent directories only under that root.
- Read and write text with an explicit encoding.
- Return clear, model-readable errors such as `ERROR: path escapes sandbox`.

Route `write_file`, `edit_file`, and `read_file` through that class. Do not
leave the old `(WORKDIR / path)` path construction in a second code path.

Add tests for safe nested paths, `../` traversal, absolute paths, and path
variants that resolve outside the workspace.

This phase prevents accidental file escape. It does not isolate processes.

## Phase 2: replace `shell=True` with a constrained command runner

Create a `SandboxRunner` interface with a method such as:

```python
def run(self, command: str, *, timeout_seconds: int) -> str:
    """Run an approved command and return a bounded text result."""
```

For the first teaching version:

- Parse commands with `shlex` or accept a command name plus argument list;
  do not send arbitrary model text to `shell=True`.
- Permit a small allowlist, for example `python`, `pytest`, or an explicit
  workshop command supplied by configuration.
- Run with the sandbox workspace as the current directory.
- Apply a timeout and cap captured stdout/stderr size.
- Return the exit code, standard output, and standard error in a bounded
  result so the model can fix failures.

On Windows, a process launched this way still runs with the user account. It is
a safer command interface, but it is not a strong operating-system sandbox.
Document that distinction in the UI and workshop material.

## Phase 3: use a real isolated runtime for untrusted execution

Select one supported runtime before claiming that execution is sandboxed.
Options include a Docker or Podman container with a bind-mounted, dedicated
workspace; a disposable virtual machine; or an operating-system sandbox service
available in the workshop environment.

The selected runtime should enforce all of the following:

- A fresh or resettable filesystem workspace per session.
- No host-home-directory mount and no broad repository mount.
- A non-root user inside the runtime.
- Network disabled by default.
- CPU, memory, process-count, output-size, and wall-clock limits.
- A read-only base image with only the workshop language/runtime installed.
- Explicit cleanup after the session.

`SandboxRunner.run()` becomes an adapter that starts the chosen runtime. The
agent and model continue to use the same tool names. Add an integration test
that proves a created file is visible inside the sandbox and unavailable on the
host outside the mounted sandbox directory.

## Phase 4: make hooks useful for sandbox policy and audit

Extend `AgentContext` with a small, append-only event list or a dedicated
`SandboxEvent` record. Avoid having hooks modify `messages`, tool arguments, or
the tool registry.

Use the existing callbacks as follows:

| Hook | Sandbox use |
| --- | --- |
| `before_tool_execute` | Record requested tool, arguments, step, sandbox session ID, and policy decision. Request human approval for a configured class of action. |
| `after_tool_execute` | Record success/failure, elapsed time, exit code, and bounded output size. |
| `on_error` | Record path-policy, runtime-startup, timeout, and process errors with a clear phase. |
| `on_session_start` | Create a sandbox session and record its identifier. |
| `on_session_stop` | Destroy or reset the sandbox and record cleanup success. |
| `before_compact` / `after_compact` | Later: preserve a short audit summary when conversation history is compacted. |

If approval is introduced, use a host-owned policy method that returns an
explicit allow/deny decision. A hook can request or record that decision, but
`ToolExecutor` must check the decision immediately before running the tool.

## Phase 5: keep the UI abstraction intact

Continue the Chapter 02 rule: `agent.py` reports an event; `UI` decides how it
is shown; `ui.json` supplies labels and Rich styles.

Add UI events such as:

```text
[box] sandbox session started
[lock] path rejected
[wait] command timed out
[ok] sandbox cleaned up
```

Use portable ASCII variants if the target Windows terminal cannot reliably
render Unicode. Do not print directly from sandbox code or hooks. Add a
`UI.show_sandbox_status()` method if sandbox messages need a richer panel than
the current one-line lifecycle trace.

## Tests and acceptance criteria

Add focused tests before enabling each phase:

1. **Workspace tests:** traversal and absolute paths fail; valid nested paths
   remain inside the dedicated root.
2. **Runner tests:** disallowed commands, shell metacharacters, timeouts, and
   oversized output produce bounded `ERROR:` results without starting a host
   shell.
3. **Hook tests:** a recording hook sees the request, decision, outcome, and
   cleanup events in order. A failing observer cannot bypass enforcement.
4. **Runtime integration tests:** the actual container/VM has no network by
   default, has the configured limits, and exposes only the dedicated mount.
5. **Cleanup tests:** session shutdown removes or resets temporary sandbox
   state, including after a tool timeout or an exception.

The sandbox can be described as a security boundary only after the real
isolated-runtime tests pass. Before that point, call it a constrained local
runner.

## Suggested implementation order

1. Add `SandboxWorkspace` and its path-validation tests.
2. Route the three file tools through it.
3. Add a non-shell, allowlisted local `SandboxRunner` with timeout/output
   limits and tests.
4. Introduce session setup/cleanup hooks and audit records.
5. Add sandbox-specific UI configuration and trace output.
6. Choose and integrate a container or VM runtime.
7. Add runtime integration and cleanup tests, then update the README and book
   to describe the proven guarantees accurately.

This sequence gives students a working improvement at each stage while making
the boundary between hook-based observability and host-enforced isolation clear.
