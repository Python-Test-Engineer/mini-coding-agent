"""Mini coding agent - the host loop that drives everything else.

A real ReAct loop: type a request, and the agent uses its tools
(write/edit/read files, run commands) until it has an answer.

    think -> tool call -> result -> repeat -> final answer

This file is deliberately small: it owns *when* things happen and nothing else.
Every other module in ``src/`` owns one responsibility, and the loop calls them:

    main()                     interactive session; wraps everything in session hooks
      +- agent_loop()          one user request (the function below)
           +- brain.chat()         ask the model and read the usage numbers
           +- tools.bind_tools()   the four host tools the model may request
           +- sandbox.py           enforces paths and commands where they run
           +- lifecycle.py         optional observers of each transition
           +- ui.py + ui.json      every line the user sees, and its wording/colour
           +- agent_logging.py     the JSONL audit trail under logs/

The loop never prints and never formats: it raises events and hands them to the
UI. The loop also never decides policy itself: a tool call either returns text
or raises, and the sandbox decides which.

Settings are loaded from the repository-root .env; explicitly exported process
environment variables take precedence.

Run:  cd src && uv run agent.py "write a hello world script and run it"

After each answer, the app prompts for a follow-up and keeps the conversation
history. Type "exit" or "quit" to end the session.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from brain import (
    SYSTEM_PROMPT,
    accumulate_usage,
    chat,
    load_env,
    model_name,
    new_metrics,
)
from lifecycle import Hooks
from sandbox import (
    ConstrainedLocalRunner,
    SandboxAuditHooks,
    SandboxCommandError,
    SandboxForbiddenError,
    SandboxPathError,
    SandboxWorkspace,
)
from tools import bind_tools
from ui import UI

# --------------------------------------------------------------------------
# WIRING (the objects and constants the loop runs with)
# --------------------------------------------------------------------------
# One UI instance shares a single Rich console for the whole conversation.
ui = UI()

# The default hook records each sandbox session and tool outcome. Applications
# can replace it with their own Hooks subclass when they need other behaviour.
hooks = SandboxAuditHooks()

# A write or edit outside work/ and logs/ is a hard stop, not a retryable tool
# error: the process prints a red [FORBIDDEN] banner and exits with this code.
# A non-zero status lets scripts and CI treat a blocked write as a failure,
# and exiting (rather than continuing the loop) makes it impossible to sneak
# the same request through with a different path in the next step.
FORBIDDEN_EXIT_CODE = 2

# The host can write agent files only under work/ and append audit records only
# under logs/. Reads may use an explicit absolute path outside those roots.
ROOT_DIR = Path(__file__).resolve().parent.parent
WORKDIR = ROOT_DIR / "work"
LOGDIR = ROOT_DIR / "logs"

# The two enforcing objects. Everything the model asks for travels through one
# of them: SandboxWorkspace owns file paths, ConstrainedLocalRunner owns
# commands. A future container or VM replaces them for untrusted prompts
# without changing this loop.
WORKSPACE = SandboxWorkspace(WORKDIR, LOGDIR)
RUNNER = ConstrainedLocalRunner(WORKSPACE)

# Load the project .env once, before the first model request needs a key. The
# helper in brain.py keeps the documented precedence: real environment
# variables win over the file.
load_env(ROOT_DIR)


# --------------------------------------------------------------------------
# TURN CONTEXT AND HOOK DISPATCH
# --------------------------------------------------------------------------
@dataclass
class AgentContext:
    """State that lifecycle callbacks may inspect during one agent turn."""

    request: str
    messages: list[dict]
    metrics: dict[str, Any]
    ui: UI
    workspace: SandboxWorkspace
    step: int = 0


def _call_hook(
    lifecycle_hooks: Hooks,
    hook_name: str,
    context: AgentContext,
    *args: Any,
    detail: str = "",
) -> None:
    """Run one extension callback while keeping extension failures contained."""
    # The UI owns presentation. The agent provides only an event name and a
    # short fact about the transition, so terminal wording stays configurable.
    context.workspace.record(f"lifecycle.{hook_name}", detail, context.step)
    context.ui.show_lifecycle_event(hook_name, detail)
    callback: Callable[..., None] | None = getattr(lifecycle_hooks, hook_name, None)
    if callback is None:
        return
    try:
        callback(context, *args)
    except Exception as error:
        # A plugin is optional: report its failure through the UI, then allow
        # the host-controlled agent loop to continue. Do not recurse into
        # ``on_error`` if that callback itself is the failed hook.
        context.workspace.record("lifecycle.hook_error", f"{hook_name}: {error}", context.step)
        context.ui.show_hook_error(hook_name, error)


def _report_error(
    lifecycle_hooks: Hooks,
    context: AgentContext,
    error: Exception,
    phase: str,
) -> None:
    """Tell hooks about a caught host error without risking recursive hooks."""
    context.workspace.record("lifecycle.error", f"{phase}: {error}", context.step)
    if isinstance(error, SandboxPathError):
        context.ui.show_sandbox_status("path_rejected", str(error))
    elif isinstance(error, SandboxCommandError):
        status = "command_timed_out" if "timed out" in str(error) else "command_rejected"
        context.ui.show_sandbox_status(status, str(error))
    context.ui.show_lifecycle_event("on_error", f"{phase}: {error}")
    callback: Callable[..., None] | None = getattr(lifecycle_hooks, "on_error", None)
    if callback is None:
        return
    try:
        callback(context, error, phase)
    except Exception as hook_error:
        context.ui.show_hook_error("on_error", hook_error)


# --------------------------------------------------------------------------
# THE LOOP
# --------------------------------------------------------------------------
def agent_loop(
    prompt: str,
    max_steps: int = 8,
    lifecycle_hooks: Hooks | None = None,
    messages: list[dict] | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    """Run one request, optionally extending a longer conversation history."""
    active_hooks = lifecycle_hooks if lifecycle_hooks is not None else hooks
    ui.show_start(prompt)
    # Reuse these objects between turns so follow-ups retain history and
    # lifecycle hooks can inspect the same session-wide usage totals.
    if messages is None:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if metrics is None:
        metrics = new_metrics()
    messages.append({"role": "user", "content": prompt})

    # The context is the single object every hook receives, and it is also
    # where the loop reads the workspace the tools must enforce against.
    context = AgentContext(prompt, messages, metrics, ui, WORKSPACE)

    # Bind the tool functions to the host objects for this turn. Doing it here
    # (rather than once at import time) keeps the tool map and the enforcing
    # workspace or runner in step, even when a caller supplies its own.
    tools = bind_tools(context.workspace, RUNNER)

    ui.show_sandbox_status("local_runner", "writes: work/ and logs/; no host shell")
    _call_hook(active_hooks, "before_input", context, prompt, detail=f"{len(prompt)} characters")
    _call_hook(active_hooks, "before_loop", context, detail="waiting for a model response")

    # One iteration of this loop is one "step": one model request, plus any
    # tools that model request asked for.
    for step in range(1, max_steps + 1):
        context.step = step

        # --- think: ask the model, and record the usage it billed ------------
        _call_hook(
            active_hooks,
            "before_brain_request",
            context,
            messages,
            detail=f"step {step} - {len(messages)} messages",
        )
        reply = chat(messages)
        accumulate_usage(metrics, reply.get("usage") or {})
        msg = reply["choices"][0]["message"]
        response_tool_count = len(msg.get("tool_calls") or [])
        _call_hook(
            active_hooks,
            "after_brain_response",
            context,
            msg,
            detail=f"step {step} - {response_tool_count} tool call(s)",
        )

        # Any prose in the reply is the model thinking aloud for the user.
        if msg.get("content"):
            ui.show_thought(step, msg["content"])

        # --- no tool calls: the request is finished ---------------------------
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            output = msg.get("content") or ""
            # Save the final response so the user's next turn has context.
            messages.append(msg)
            _call_hook(active_hooks, "after_loop", context, output, detail="final response received")
            _call_hook(active_hooks, "after_input", context, prompt, output, detail="request complete")
            ui.blank_line()
            ui.show_done(metrics)
            return

        # --- act: run each requested tool and send its result back ------------
        # Preserve the assistant's tool request before replying with tool results.
        messages.append(msg)
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                # Return malformed arguments as an empty object so the loop can continue.
                args = {}
                _report_error(
                    active_hooks,
                    context,
                    ValueError(f"Malformed arguments for tool {name}"),
                    "tool_arguments",
                )
            ui.show_tool(name, args)
            if name == "write_file":
                ui.show_code(args.get("content", ""))
            _call_hook(
                active_hooks,
                "before_tool_execute",
                context,
                name,
                args,
                detail=f"{name} - {len(args)} argument(s)",
            )
            try:
                # The host runs the tool; the model only asked for it. The
                # sandbox inside the bound function decides whether it is
                # allowed, and raises when it is not.
                result = tools[name](**args)
            except Exception as e:  # surface tool errors back to the model
                _report_error(active_hooks, context, e, "tool_execute")
                result = f"ERROR: {e}"
                # Only an outside write/edit target is fatal. A missing file or
                # a refused command stays a normal tool error the model can fix.
                # The sandbox already announced the red FORBIDDEN banner at the
                # point of detection, so nothing is printed here.
                forbidden = isinstance(e, SandboxForbiddenError)
            else:
                forbidden = False
            tool_status = "failed" if result.startswith("ERROR:") else "complete"
            _call_hook(
                active_hooks,
                "after_tool_execute",
                context,
                name,
                result,
                detail=f"{name} - {tool_status}",
            )
            ui.show_result(result)
            messages.append(
                {"role": "tool", "tool_call_id": tc["id"], "content": result}
            )
            if forbidden:
                # A write/edit target outside work/ and logs/ stops the whole
                # process. Turn hooks still run first so the audit log records
                # the blocked request; then the program exits with a non-zero
                # code. Raising SystemExit (not ``return``) is what makes this
                # a hard stop: neither the loop nor the interactive prompt can
                # continue, so the model never gets a chance to retry with a
                # slightly different path.
                output = f"Forbidden file operation: {result}"
                _call_hook(
                    active_hooks,
                    "after_loop",
                    context,
                    output,
                    detail="forbidden file operation",
                )
                _call_hook(
                    active_hooks,
                    "after_input",
                    context,
                    prompt,
                    output,
                    detail="request blocked",
                )
                ui.blank_line()
                ui.show_done(metrics)
                # Hard stop: exit the entire process with a failure status so
                # nothing after this point can run in the same session.
                raise SystemExit(FORBIDDEN_EXIT_CODE)
        # End of this step's tool results: the model reads them on the next step.
        ui.blank_line()

    # The step budget ran out before the model produced a final answer.
    _call_hook(active_hooks, "after_loop", context, "", detail="maximum steps reached")
    _call_hook(active_hooks, "after_input", context, prompt, "", detail="request complete")
    ui.show_max_steps(metrics)


# --------------------------------------------------------------------------
# THE INTERACTIVE SESSION
# --------------------------------------------------------------------------
def _read_prompt() -> str | None:
    """Read one user request, returning ``None`` when input is closed."""
    try:
        # The prompt line, including the model name, is the UI's to draw.
        return ui.prompt(model_name()).strip()
    except (EOFError, KeyboardInterrupt):
        # EOF (for example, piped input ending) and Ctrl+C both end cleanly.
        ui.blank_line()
        return None


def main() -> None:
    """Run one interactive session, accepting follow-up requests until exit."""
    # A command-line request starts the session; otherwise ask for its first turn.
    prompt = " ".join(sys.argv[1:]).strip()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    metrics = new_metrics()
    session_context = AgentContext(prompt or "", messages, metrics, ui, WORKSPACE)
    _call_hook(hooks, "on_session_start", session_context, detail="interactive session")
    # The exit/quit wording is configured in ui.json, not written here.
    ui.show_hint()
    try:
        if not prompt:
            prompt = _read_prompt()

        while prompt is not None:
            # Ignore empty lines and let the user keep entering requests.
            if not prompt:
                prompt = _read_prompt()
                continue
            if prompt.lower() in {"exit", "quit"}:
                break

            # Keep the session context current while each turn gets its own
            # hook context and its own eight-step model/tool budget.
            session_context.request = prompt
            agent_loop(prompt, messages=messages, metrics=metrics)
            prompt = _read_prompt()
    finally:
        _call_hook(hooks, "on_session_stop", session_context, detail="interactive session")
        ui.show_sandbox_status("session_stopped", "constrained local runner stopped")


if __name__ == "__main__":
    main()
