# Plan: use lifecycle hooks with a constrained tool host

## Goal

Constrain agent file tools to approved repository folders, record lifecycle
events, and reduce shell risks while keeping the Python host responsible for
every tool operation. The current implementation is a constrained local
runner; a container or VM is still needed for an operating-system security
boundary.

Lifecycle hooks help make this work visible, auditable, and testable. They do
not create a security boundary by themselves. The security boundary must be
enforced by the code that resolves file paths and starts processes.

## Current position

`src/agent.py` exposes four host tools:

- `write_file` and `edit_file` allow targets only under repository-root
  `work/` or `logs/`.
- `read_file` accepts work-relative paths and any readable absolute path.
- `run` uses an allowlisted command parser and `subprocess.run(...,
  shell=False, cwd=work/)` with a timeout and bounded output.

The host file tools reject write/edit paths outside the two approved roots and
there is no delete tool. These rules do not constrain arbitrary Python code
started by `run`: a process still has the current user's OS permissions.

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

## Implemented shape

```text
model tool request
      |
      v
before_tool_execute hook  ---> audit event / optional approval request
      |
      v
SandboxWorkspace / ConstrainedLocalRunner (host-enforced tool policy)
      |-- permit write/edit only under work/ and logs/
      |-- permit reads from readable absolute paths
      |-- run allowlisted commands without a shell
      v
work/ or logs/ / local process
      |
      v
after_tool_execute hook   ---> audit result / JSONL log / UI trace
```

The `SandboxWorkspace` is the only route for model-requested file operations.
The runner constrains command syntax but does not isolate the child process.
Hooks surround these operations and write lifecycle events to `logs/*.jsonl`.

## Phase 1: constrain host file tools (implemented)

`SandboxWorkspace` uses repository-root `work/` for ordinary files and
repository-root `logs/` for audit records.

Its responsibilities are:

- Resolve write/edit paths and allow only descendants of `work/` or `logs/`.
- Reject absolute, drive-qualified, and traversal targets outside those roots.
- Keep normal bare relative file names rooted in `work/`; accept `logs/...`
  for explicit log files.
- Allow `read_file` to read an absolute path wherever the current user can read.
- Create parent directories only under an approved writable root.
- Read and write text with an explicit encoding.
- Return a clear model-readable error when a write/edit target is outside the
  allowed roots.

Route `write_file`, `edit_file`, and `read_file` through that class. Do not
leave the old `(WORKDIR / path)` path construction in a second code path.

Tests verify work/log writes, external absolute reads, and rejection of
external write/edit attempts. There is no delete tool in the registered tool
map, so a model cannot request deletion through the agent file API.

This phase constrains the built-in file tools. It does not restrict writes made
by arbitrary code launched through the local process runner.

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
- Run with `work/` as the current directory.
- Apply a timeout and cap captured stdout/stderr size.
- Return the exit code, standard output, and standard error in a bounded
  result so the model can fix failures.

The local runner currently applies these rules with `shell=False`, an allowlist
of Python and pytest executable names, a 20-second timeout, a 12,000-character
cap for each output stream, and rejects parent/absolute path arguments and
inline Python `-c` commands. These are command-interface constraints only. A
Python script or pytest test can still use its process permissions to write
outside `work/` and `logs/`.

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

## Phase 4: record lifecycle and tool events (implemented)

`AgentContext` exposes the `SandboxWorkspace`. Each lifecycle callback appends
a `SandboxEvent` to memory and writes a JSONL record to a uniquely named file
in `logs/`. The record contains an event name, detail, step, monotonic time,
and UTC timestamp. The event log file is created when the workspace starts.

Use the existing callbacks as follows:

| Hook | Sandbox use |
| --- | --- |
| `before_tool_execute` | Record the requested tool name, argument count, and step. |
| `after_tool_execute` | Record the tool name and success/failure outcome. |
| `on_error` | Record path-policy, timeout, process, and tool errors with their phase. |
| `on_session_start` | Record the start of the local runner session. |
| `on_session_stop` | Record the end of the local runner session. |
| Every callback | Record its lifecycle name and short detail in JSONL. |
| `before_compact` / `after_compact` | Later: preserve a short audit summary when conversation history is compacted. |

If approval is introduced, use a host-owned policy method that returns an
explicit allow/deny decision. A hook can request or record that decision, but
`ToolExecutor` must check the decision immediately before running the tool.

## Phase 5: keep the UI abstraction intact

Continue the Chapter 02 rule: `agent.py` reports an event; `UI` decides how it
is shown; `ui.json` supplies labels and Rich styles.

The UI displays policy statuses such as:

```text
sandbox | [box] constrained local runner
sandbox | [lock] path rejected
sandbox | [wait] command timed out
```

Use portable ASCII variants if the target Windows terminal cannot reliably
render Unicode. Do not print directly from sandbox code or hooks. Add a
`UI.show_sandbox_status()` method if sandbox messages need a richer panel than
the current one-line lifecycle trace.

## Tests and acceptance criteria

Add focused tests before enabling each phase:

1. **Workspace tests:** writes/edits under `work/` and `logs/` succeed;
   external writes and edits fail; readable absolute paths succeed.
2. **Runner tests:** disallowed commands, shell metacharacters, timeouts, and
   oversized output produce bounded `ERROR:` results without starting a host
   shell.
3. **Hook/log tests:** lifecycle and tool events appear as JSONL records under
   `logs/`; a failing observer cannot bypass host file-tool enforcement.
4. **Runtime integration tests:** the actual container/VM has no network by
   default, has the configured limits, and exposes only the dedicated mount.
5. **Cleanup tests:** session shutdown removes or resets temporary sandbox
   state, including after a tool timeout or an exception.

The implementation can guarantee the path policy for registered file tools.
It cannot guarantee that a child Python process writes only under `work/` and
`logs/`. Describe the current setup as a constrained local runner. Claim a
whole-agent filesystem security boundary only after a container or VM enforces
the same roots and its integration tests pass.

## Suggested implementation order

1. **Done:** constrain built-in writes/edits to `work/` and `logs/`; permit
   readable absolute paths; omit any delete tool.
2. **Done:** use a non-shell allowlisted local runner with timeout/output
   limits and tests.
3. **Done:** append lifecycle/tool events to JSONL files in `logs/` and show
   configured UI statuses.
4. Choose and integrate a container or VM runtime that enforces filesystem,
   network, user, and resource limits for executed code.
5. Add runtime integration tests proving child code cannot write outside
   `work/` and `logs/`, then update the safety documentation to match.

This sequence gives students a working improvement at each stage while making
the boundary between hook-based observability and host-enforced isolation clear.
