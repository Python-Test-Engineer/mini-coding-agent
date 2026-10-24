"""Mini coding agent — a tiny functional harness for the AI-agents talk.

A real ReAct loop: type a request, and the agent uses its tools
(write/edit/read files, run commands) until it has an answer.

    think -> tool call -> result -> repeat -> final answer

LLM calls go to OpenRouter. Settings are loaded from the repository-root .env;
explicit process environment variables take precedence.

Run:  cd src && uv run agent.py "write a hello world script and run it"

After each answer, the app prompts for a follow-up and keeps the conversation
history. Type "exit" or "quit" to end the session.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from lifecycle import Hooks
from sandbox import (
    ConstrainedLocalRunner,
    SandboxAuditHooks,
    SandboxCommandError,
    SandboxError,
    SandboxPathError,
    SandboxWorkspace,
)
from ui import UI

# One UI instance shares a single Rich console for the whole conversation.
ui = UI()

# The default hook records each sandbox session and tool outcome. Applications
# can replace it with their own Hooks subclass when they need other behaviour.
hooks = SandboxAuditHooks()

# The host can write agent files only under work/ and append audit records only
# under logs/. Reads may use an explicit absolute path outside those roots.
ROOT_DIR = Path(__file__).resolve().parent.parent
WORKDIR = ROOT_DIR / "work"
LOGDIR = ROOT_DIR / "logs"
WORKSPACE = SandboxWorkspace(WORKDIR, LOGDIR)
RUNNER = ConstrainedLocalRunner(WORKSPACE)


def _load_dotenv() -> None:
    """Load project settings without overriding explicitly exported values."""
    load_dotenv(ROOT_DIR / ".env", override=False)


_load_dotenv()


# --------------------------------------------------------------------------
# TOOLS — the only things the agent can do (mirrors real coding agents)
# --------------------------------------------------------------------------
def write_file(path: str, content: str) -> str:
    """Create UTF-8 text only under work/ or logs/."""
    return WORKSPACE.write_file(path, content)


def edit_file(path: str, old: str, new: str) -> str:
    """Edit UTF-8 text only under work/ or logs/."""
    return WORKSPACE.edit_file(path, old, new)


def read_file(path: str) -> str:
    """Read a work-relative file or any readable file at an absolute path."""
    return WORKSPACE.read_file(path)


def run(command: str) -> str:
    """Run an allowlisted command without using a host shell.

    This is a constrained local runner, not a strong OS-level sandbox. A future
    container or VM runner can implement the same interface for untrusted code.
    """
    return RUNNER.run(command)


TOOLS = {
    "write_file": write_file,
    "edit_file": edit_file,
    "read_file": read_file,
    "run": run,
}

# The schema tells the model which host functions it may ask the agent to call.
# Python still decides what actually runs; the model does not execute tools itself.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file only in work/ or logs/.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace text only in a file under work/ or logs/.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                },
                "required": ["path", "old", "new"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a work-relative file or any readable absolute path.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run",
            "description": "Run an allowlisted command without a shell (e.g. 'python hello.py').",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are a minimal coding agent. You can write, edit and read files "
    "in work/ or logs/, read files when needed, and run allowlisted commands in work/. "
    "Never redirect or silently change a requested write destination. If the user "
    "asks to create or edit a file outside work/ or logs/, do not write it anywhere; "
    "attempt the requested path only so the host can reject it and show a warning, "
    "then explain that the operation was blocked. "
    "Work step by step: "
    "create the script, run it, fix any errors, and confirm the final output. "
    "Finish with a short plain-text summary of what you did."
)


# --------------------------------------------------------------------------
# LLM (OpenRouter, OpenAI-compatible chat completions)
# --------------------------------------------------------------------------
def _api_key() -> str:
    # The project .env is loaded once; shell environment variables take precedence.
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    raise SystemExit("No OPENROUTER_API_KEY found (set it in the root .env or environment).")


def _model() -> str:
    # Keep the same precedence as the API key: environment, .env, fallback.
    return os.environ.get("MODEL") or "deepseek/deepseek-v4.1-flash"


def chat(messages: list[dict]) -> dict:
    # OpenRouter accepts the OpenAI chat-completions request/response format.
    body = json.dumps(
        {
            "model": _model(),
            "messages": messages,
            "tools": TOOL_SCHEMAS,
        }
    ).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def _accumulate_usage(metrics: dict, usage: dict) -> None:
    # Keep the most recent prompt size for context display and sum billed usage.
    prompt_tokens = usage.get("prompt_tokens")
    if prompt_tokens is not None:
        prompt_tokens = int(prompt_tokens)
        metrics["last_input_tokens"] = prompt_tokens
        metrics["total_input_tokens"] += prompt_tokens

    completion_tokens = usage.get("completion_tokens")
    if completion_tokens is not None:
        metrics["total_output_tokens"] += int(completion_tokens)

    cost = usage.get("cost")
    if cost is not None:
        metrics["total_cost"] += float(cost)

    context_limit = usage.get("context_limit")
    if context_limit is not None:
        metrics["context_limit"] = int(context_limit)


def _new_metrics() -> dict:
    """Create usage totals shared by all requests in one session."""
    return {
        "last_input_tokens": 0,
        "context_limit": None,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost": 0.0,
    }


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
    # The UI owns presentation.  The agent provides only an event name and a
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
        # the host-controlled agent loop to continue.  Do not recurse into
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
        metrics = _new_metrics()
    messages.append({"role": "user", "content": prompt})

    context = AgentContext(prompt, messages, metrics, ui, WORKSPACE)
    ui.show_sandbox_status("local_runner", "writes: work/ and logs/; no host shell")
    _call_hook(active_hooks, "before_input", context, prompt, detail=f"{len(prompt)} characters")
    _call_hook(active_hooks, "before_loop", context, detail="waiting for a model response")

    for step in range(1, max_steps + 1):
        context.step = step
        _call_hook(
            active_hooks,
            "before_brain_request",
            context,
            messages,
            detail=f"step {step} - {len(messages)} messages",
        )
        reply = chat(messages)
        _accumulate_usage(metrics, reply.get("usage") or {})
        msg = reply["choices"][0]["message"]
        response_tool_count = len(msg.get("tool_calls") or [])
        _call_hook(
            active_hooks,
            "after_brain_response",
            context,
            msg,
            detail=f"step {step} - {response_tool_count} tool call(s)",
        )

        if msg.get("content"):
            ui.show_thought(step, msg["content"])

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
                result = TOOLS[name](**args)
            except Exception as e:  # surface tool errors back to the model
                _report_error(active_hooks, context, e, "tool_execute")
                result = f"ERROR: {e}"
                forbidden = isinstance(e, SandboxPathError) and name in {
                    "write_file",
                    "edit_file",
                }
                if forbidden:
                    ui.show_forbidden(str(e))
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
                # Stop this turn immediately so the model cannot retry the
                # rejected request by silently changing its destination.
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
                return
        ui.blank_line()

    _call_hook(active_hooks, "after_loop", context, "", detail="maximum steps reached")
    _call_hook(active_hooks, "after_input", context, prompt, "", detail="request complete")
    ui.show_max_steps(metrics)


def _read_prompt() -> str | None:
    """Read one user request, returning ``None`` when input is closed."""
    try:
        return ui.prompt(_model()).strip()
    except (EOFError, KeyboardInterrupt):
        # EOF (for example, piped input ending) and Ctrl+C both end cleanly.
        ui.blank_line()
        return None


def main() -> None:
    """Run one interactive session, accepting follow-up requests until exit."""
    # A command-line request starts the session; otherwise ask for its first turn.
    prompt = " ".join(sys.argv[1:]).strip()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    metrics = _new_metrics()
    session_context = AgentContext(prompt or "", messages, metrics, ui, WORKSPACE)
    _call_hook(hooks, "on_session_start", session_context, detail="interactive session")
    ui.console.print("Type 'exit' or 'quit' to end the conversation.")
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

            # Keep the session context current while each turn gets its own hook context.
            session_context.request = prompt
            agent_loop(prompt, messages=messages, metrics=metrics)
            prompt = _read_prompt()
    finally:
        _call_hook(hooks, "on_session_stop", session_context, detail="interactive session")
        ui.show_sandbox_status("session_stopped", "constrained local runner stopped")


if __name__ == "__main__":
    main()
