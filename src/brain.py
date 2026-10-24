"""The model side of the agent: prompts, tool schemas, and the HTTP call.

``brain.py`` is deliberately the only file that knows how to talk to an LLM.
It holds four things:

* ``SYSTEM_PROMPT``  - the standing instructions sent with every conversation;
* ``TOOL_SCHEMAS``   - the list of host functions the model is allowed to ask for;
* ``chat()``         - one blocking OpenRouter chat-completions request;
* usage totals (``new_metrics`` / ``accumulate_usage``) read from each reply.

Keeping this code out of ``agent.py`` means the loop there reads as the ReAct
cycle itself, and a workshop participant can swap this module for another
provider without touching the loop, the tools, or the sandbox policy.

The host still decides what runs: the model only *requests* a tool by name, and
``agent.py`` looks that name up in the registry built by ``tools.py``.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# The repository root, two levels above this file, is where .env lives. Loading
# uses this value at call time so a test can point it at a temporary folder.
ROOT_DIR = Path(__file__).resolve().parent.parent

# One place to change provider or version if OpenRouter moves its endpoint.
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# The fallback model keeps the demo runnable with an API key alone; the MODEL
# environment variable (or the .env file) overrides it.
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"


def load_env(root: Path | None = None) -> None:
    """Load project settings from ``root/.env`` without overriding the shell.

    ``override=False`` keeps the documented precedence: a variable that is
    already exported in the environment always wins over the .env file.
    """
    load_dotenv((root or ROOT_DIR) / ".env", override=False)


def api_key() -> str:
    """Return the OpenRouter key, or stop with a readable message.

    Secrets stay in the environment or the ignored .env file; this is the only
    place in the project that reads them.
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    raise SystemExit("No OPENROUTER_API_KEY found (set it in the root .env or environment).")


def model_name() -> str:
    """Return the configured model id, falling back to the demo default."""
    # Same precedence as the API key: environment, then .env, then fallback.
    return os.environ.get("MODEL") or DEFAULT_MODEL


# --------------------------------------------------------------------------
# THE MODEL-VISIBLE CONTRACT
# --------------------------------------------------------------------------
# The system prompt explains the rules; the schemas below explain the syntax.
# TOOL_SCHEMAS mirrors the functions registered by ``tools.py``: the names here
# must match the keys of the bound tool map, or the model will ask for a tool
# the host cannot find.
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

TOOL_SCHEMAS: list[dict[str, Any]] = [
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


# --------------------------------------------------------------------------
# ONE MODEL REQUEST (OpenRouter, OpenAI-compatible chat completions)
# --------------------------------------------------------------------------
def chat(messages: list[dict]) -> dict:
    """Send the conversation and the tool schemas, and return the raw reply.

    The reply is the provider's JSON dictionary, not a simplified object, so
    the loop can read ``choices[0].message`` and ``usage`` exactly as sent.
    """
    # OpenRouter accepts the OpenAI chat-completions request/response format.
    body = json.dumps(
        {
            "model": model_name(),
            "messages": messages,
            "tools": TOOL_SCHEMAS,
        }
    ).encode()
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
        },
    )
    # A generous timeout keeps a slow model from hanging the workshop demo.
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


# --------------------------------------------------------------------------
# USAGE METRICS (what the footer shows after each request)
# --------------------------------------------------------------------------
def new_metrics() -> dict[str, Any]:
    """Create the usage totals shared by every request in one session."""
    return {
        "last_input_tokens": 0,
        "context_limit": None,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost": 0.0,
    }


def accumulate_usage(metrics: dict, usage: dict) -> None:
    """Add one reply's billed usage to the session totals.

    The most recent prompt size is kept for the context display, while prompt,
    completion and cost values are summed across the whole conversation.
    """
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
