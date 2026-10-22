"""Mini coding agent — a tiny functional harness for the AI-agents talk.

A real ReAct loop: type a request, and the agent uses its tools
(write/edit/read files, run commands) until it has an answer.

    think -> tool call -> result -> repeat -> final answer

LLM calls go to OpenRouter. Settings are loaded from the repository-root .env;
explicit process environment variables take precedence.

Run:  cd src && uv run agent.py "write a hello world script and run it"
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from ui import UI

# One UI instance shares a single Rich console for the whole conversation.
ui = UI()

# Anchor generated files at the repository root, regardless of launch directory.
ROOT_DIR = Path(__file__).resolve().parent.parent
WORKDIR = ROOT_DIR / "work"
WORKDIR.mkdir(exist_ok=True)


def _load_dotenv() -> None:
    """Load project settings without overriding explicitly exported values."""
    load_dotenv(ROOT_DIR / ".env", override=False)


_load_dotenv()


# --------------------------------------------------------------------------
# TOOLS — the only things the agent can do (mirrors real coding agents)
# --------------------------------------------------------------------------
def write_file(path: str, content: str) -> str:
    (WORKDIR / path).write_text(content)
    return f"Created {path}"


def edit_file(path: str, old: str, new: str) -> str:
    p = WORKDIR / path
    p.write_text(p.read_text().replace(old, new, 1))
    return f"Edited {path}: {old!r} -> {new!r}"


def read_file(path: str) -> str:
    return (WORKDIR / path).read_text()


def run(command: str) -> str:
    # The command runs with this user's permissions; cwd alone does not restrict it.
    out = subprocess.run(
        command, shell=True, capture_output=True, text=True, cwd=WORKDIR
    )
    return out.stdout.strip() or out.stderr.strip()


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
            "description": "Create or overwrite a file in the work dir.",
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
            "description": "Replace the first occurrence of old with new in a file.",
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
            "description": "Read a file in the work dir.",
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
            "description": "Run a shell command in the work dir (e.g. 'python hello.py').",
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
    "in the work directory, and run shell commands there. Work step by step: "
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


# --------------------------------------------------------------------------
# THE LOOP
# --------------------------------------------------------------------------
def agent_loop(prompt: str, max_steps: int = 8) -> None:
    ui.show_start(prompt)
    # Messages are the shared conversation state sent again on every model call.
    metrics = {
        "last_input_tokens": 0,
        "context_limit": None,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost": 0.0,
    }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    for step in range(1, max_steps + 1):
        reply = chat(messages)
        _accumulate_usage(metrics, reply.get("usage") or {})
        msg = reply["choices"][0]["message"]

        if msg.get("content"):
            ui.show_thought(step, msg["content"])

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
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
            ui.show_tool(name, args)
            if name == "write_file":
                ui.show_code(args.get("content", ""))
            try:
                result = TOOLS[name](**args)
            except Exception as e:  # surface tool errors back to the model
                result = f"ERROR: {e}"
            ui.show_result(result)
            messages.append(
                {"role": "tool", "tool_call_id": tc["id"], "content": result}
            )
        ui.blank_line()

    ui.show_max_steps(metrics)


if __name__ == "__main__":
    # A command-line request skips the prompt; without one, ask interactively.
    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        prompt = ui.prompt(_model()).strip()
    agent_loop(prompt)
