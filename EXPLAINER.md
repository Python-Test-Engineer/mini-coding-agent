# How mini-coding-agent works

`agent.py` is a working, if small, **agentic coding loop** — the same core idea
behind Claude Code, Copilot and similar tools, stripped to nothing but the
essentials. There are no frameworks and no LLM SDKs: the only dependency is
`rich`, purely for pretty console output. Everything else is stdlib
(`urllib`, `json`, `subprocess`).

The project separates responsibilities across three files: `agent.py` owns the
model call and tool loop, `ui.py` renders the console interface, and `ui.json`
configures the UI labels and Rich styles.

The whole point is to show *what an agent actually is*: not one magic LLM call,
but a **loop** in which the model repeatedly decides what to do, the host executes
it, and the result is handed back — until the model stops asking for tools.

```
request ─▶ [ model decides ] ─▶ tool call ─▶ host runs it ─▶ result ─▶ [ model decides ]
                                  ▲                                          │
                                  └──────────── loop (max 8 steps) ──────────┘
                                          ...eventually ▶ final answer
```

---

## The four tools the agent can use

An agent can only do whatever its host exposes. Here, exactly four functions,
all sandboxed to the `work/` directory:

| Tool | Signature | What it does |
|------|-----------|--------------|
| `write_file` | `(path, content)` | Create or overwrite a file in `work/` |
| `edit_file` | `(path, old, new)` | Replace the *first* occurrence of `old` with `new` |
| `read_file` | `(path)` | Return a file's contents |
| `run` | `(command)` | Run a shell command, cwd = `work/` |

Because all I/O is locked to `work/`, the agent can write a `hello.py`, run
`python hello.py`, see an error, edit it, and re-run — a complete fix cycle.

> **Security note:** `run()` uses `shell=True` and is *not* sandboxed beyond its
> working directory. The agent can read/write anything under `work/` and execute
> arbitrary commands. Fine for a local demo; don't point this at untrusted prompts.

---

## How the loop gets the model to call tools

Modern chat models understand **tools** as part of their training. You advertise
the available functions as a JSON schema in the API request, exactly like this:

```json
{
  "type": "function",
  "function": {
    "name": "write_file",
    "description": "Create or overwrite a file in the work dir.",
    "parameters": {
      "type": "object",
      "properties": { "path": {"type": "string"}, "content": {"type": "string"} },
      "required": ["path", "content"]
    }
  }
}
```

When the model decides it needs a tool, its reply contains a `tool_calls` array
describing *which* function and *what arguments* — it does **not** execute
anything itself. That's the crucial separation:

1. The model *proposes*: "call `write_file` with these args."
2. The **host** executes the actual filesystem/system call.
3. The host appends a `role: "tool"` message containing the result.
4. The model sees the result and decides the next step.

This hand-off is why the model never touches your filesystem directly — a real
safety boundary even in a toy like this.

---

## The message history that drives it

The API is stateless — each request is a batch of messages. `agent.py` keeps
the running conversation in a plain list and re-sends it every step:

```
system   You are a minimal coding agent...
user     write a hello world script and run it
assistant  <thought>   (content, style configured in ui.json)
assistant  <tool_calls: write_file(path, content)>
tool      Created hello.py                  ← result, matched by tool_call_id
assistant  <tool_calls: run(python hello.py)>
tool      Hello, world!                     ← output of the script
assistant  <final answer, no tool_calls>    → loop ends
```

Two details worth noticing:

- **Tool results carry an `id`.** Each assistant `tool_call` has an `id`; the
  host echoes it on the corresponding `tool` message so the model can pair them.
- **The loop ends when the model returns content with no `tool_calls`.** That's
  the agent deciding it's done. There's also a hard stop at `max_steps = 8`
  (`agent_loop(prompt, max_steps=8)`) so a confused model can't loop forever.

Unlike the HTML "memory" demo (which stores chat text in `localStorage`), here
the *entire* tool conversation is the working memory — everything is re-sent
each iteration, which is why the agent can remember what it wrote earlier.

---

## Key resolution & the wire call

- Key comes from the `OPENROUTER_API_KEY` env var, falling back to
  `../OPENROUTER.txt` in the repo root; `MODEL` env var, else the `MODEL=` line,
  else `deepseek/deepseek-v4.1-flash`. (See repo-root `SETUP.md`.)
- The request is a hand-built HTTP POST to
  `https://openrouter.ai/api/v1/chat/completions` via `urllib` — no SDK. Body:
  `{ model, messages, tools }`.

---

## Running it

The Rich console rendering is kept in `ui.py`; edit `ui.json` to change the
labels or Rich styles for the prompt, panels, tools, code preview, and status
messages. The model tag in the interactive prompt uses the `input_model` style.
The `styles` values use Rich style names (for example, `bold cyan`).

```sh
cd src
uv run agent.py "write a hello world script and run it"
# or: pass nothing for an interactive prompt
# or override: MODEL=openai/gpt-4o-mini OPENROUTER_API_KEY=sk-or-... uv run agent.py "..."
```

When run without a command-line request, the prompt starts with the active model
name, for example: `[openai/gpt-6-luna] Request ›`. It uses the same model
resolution as the API call: `MODEL` from the environment, then `MODEL=` in
`OPENROUTER.txt`, then the built-in fallback.

Watch the terminal: you'll see the thought, the `tool write_file({...})` line,
the green result panels, and finally the summary. That running log *is* the
whole talk in one screenful.

---

## What a fuller agent adds (the demo's roadmap)

This is deliberately minimal. Production coding agents bolt on:

- **More tools** (read directories, run tests, git, web search) and richer tool
  result handling.
- **A real sandbox** — execute untrusted code in a container/VM, not `subprocess`.
- **Context trimming** — the full history is re-sent each step, so long runs
  blow up token costs; real agents summarize or drop old turns.
- **A planner / multi-agent split** — separate the "what to do" reasoning from
  the "which files to touch" execution.
- **Human-in-the-loop** — pause and ask before destructive commands.

The loop shape here — decide, execute, feed back, repeat — is the thing they
all share.
