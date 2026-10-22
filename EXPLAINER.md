# How mini-coding-agent works

`src/agent.py` is a small, working **agentic coding loop**: a model chooses
tools, the Python host executes them, and their results go back to the model.
It demonstrates the core pattern used by coding agents without an agent
framework or LLM SDK. The agent uses `rich` for its console interface; HTTP,
JSON, filesystem, and process operations use the Python standard library.

The app lives in `src/`: `agent.py` owns the OpenRouter request, tool functions,
agent loop, and usage tracking; `ui.py` renders the console and footer; `ui.json`
configures its labels and Rich styles; `tests/` contains the `unittest` suite;
and `work/` is the intended working directory for generated files and commands.
`demo-prompt.md` contains a sample request. The root `main.py` is only a greeting
stub; launch the actual agent with `src/agent.py`.

The whole point is to show *what an agent actually is*: not one magic LLM call,
but a **loop** in which the model repeatedly decides what to do, the host executes
it, and the result is handed back — until the model stops asking for tools.

```
request ─▶ [ model response ] ─▶ tool call ─▶ host runs it ─▶ result ─▶ [ model response ]
                                      ▲                                           │
                                      └──────────── loop (max 8 steps) ──────────┘
                                                 ...no more tools ▶ done
```

---

## The four tools the agent can use

An agent can only do whatever its host exposes. Here, exactly four functions
are exposed. `work/` is the intended working directory, but not a security sandbox:

| Tool | Signature | What it does |
|------|-----------|--------------|
| `write_file` | `(path, content)` | Write text to a file path |
| `edit_file` | `(path, old, new)` | Replace the first occurrence of `old` in a file |
| `read_file` | `(path)` | Return a file's text contents |
| `run` | `(command)` | Run a shell command with `work/` as its current directory |

The agent anchors `WORKDIR` to the repository root, so it can create
`work/hello.py` even when launched from `src/`, run `python hello.py`, inspect
the output, edit the script, and run it again — a complete fix cycle. `run()`
uses `work/` as the command's current directory and returns stdout, or stderr if
stdout is empty; it does not report the process exit code separately.

> **Security note:** `work/` is only the default working directory, not a
> sandbox. File tools do not check that paths stay inside it, and `run()` uses
> `shell=True`, so commands can access files and run programs outside it. Use
> only with trusted prompts in a controlled demo; do not expose this app to
> untrusted users or treat it as a secure coding agent.

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

When the model requests a tool, its reply contains a `tool_calls` array
describing *which* function and *what arguments* — it does **not** execute
anything itself. That's the crucial separation:

1. The model *proposes*: "call `write_file` with these args."
2. The **host** executes the actual filesystem/system call.
3. The host appends a `role: "tool"` message containing the result.
4. The model sees the result and returns another response, either requesting
   more tools or ending the loop.

The model does not execute Python functions itself, but the host executes its
requested operations with the permissions of the user running the app. This
separation is how tool calling works; it is not a security boundary.

---

## The message history that drives it

The API is stateless — each request is a batch of messages. `agent.py` keeps
the running conversation in a plain list and re-sends it every step:

```
system   You are a minimal coding agent...
user     write a hello world script and run it
assistant  <text>      (rendered with the thought label configured in ui.json)
assistant  <tool_calls: write_file(path, content)>
tool      Created hello.py                  ← result, matched by tool_call_id
assistant  <tool_calls: run(python hello.py)>
tool      Hello, world!                     ← output of the script
assistant  <final answer, no tool_calls>    → loop ends
```

Two details worth noticing:

- **Tool results carry an `id`.** Each assistant `tool_call` has an `id`; the
  host echoes it on the corresponding `tool` message so the model can pair them.
- **The loop ends when the model returns no `tool_calls`.** The app also stops
  after at most eight model-response iterations (`max_steps=8`), even if the
  model keeps requesting tools.

Unlike the HTML "memory" demo (which stores chat text in `localStorage`), here
the *entire* tool conversation is the working memory — everything is re-sent
each iteration, which is why the agent can remember what it wrote earlier.

---

## Configuration & the API call

- The API key comes from `OPENROUTER_API_KEY` in the environment, or from the
  `OPENROUTER_API_KEY=` line in the repo-root `OPENROUTER.txt` file. The model
  comes from the `MODEL` environment variable, then the `MODEL=` line in that
  file, then the built-in default `deepseek/deepseek-v4.1-flash`.
- `agent.py` sends an HTTP POST to
  `https://openrouter.ai/api/v1/chat/completions` using `urllib.request`. The
  JSON request contains the selected model, message history, and tool schemas.
  The system prompt asks the model to work step by step, run and fix its code,
  and finish with a short plain-text summary.

---

## Console UI and configuration

### How `ui.py` uses Rich

`ui.py` defines a `UI` class around Rich's `Console`. Rich handles terminal
layout and styling so the app can show structured output rather than plain,
unformatted log lines. The UI can use the default console or accept a `Console`
and config path when constructed. By default, it reads `ui.json` from beside
`ui.py` as UTF-8 JSON, then uses its `labels` and `styles` dictionaries.

Each `UI` method renders one part of the interaction:

- `prompt()` builds a Rich `Text` prompt from the model name, request label,
  and indicator, then uses `Console.input()` to read the user's request.
- `show_start()` draws a `Console.rule()` header and puts the request in a
  `Panel`; `show_thought()` displays the model's text in a step-labelled panel.
- `show_tool()` builds a `Text` line with the tool name and JSON arguments.
- `show_code()` uses Rich `Syntax` to display file content with Python
  highlighting and the configured theme.
- `show_result()` puts tool output in a result `Panel`; `show_done()` and
  `show_max_steps()` render the completion and step-limit messages, then call
  `footer()` to show token and cost usage.
- `footer()` shows the latest prompt size, totals for prompt and completion
  tokens, and cumulative cost. It shows context-window percentage only when a
  context limit is available; otherwise it labels the limit as unavailable.

Rich components take styles separately from their text: for example, a
`Panel` has a title style and border style, while a `Text` object can style
individual spans. This is how the interface highlights the model prompt,
tools, code and results without mixing terminal escape codes into agent logic.

### What `ui.json` controls

`ui.json` is the UI's visual and wording configuration, not the agent's
behavior. Its `labels` values supply the text shown by `ui.py`; `{model}` is
substituted into the model prompt label and `{step}` into the thought-panel
title. Its `styles` values are Rich style strings: for example, `bold cyan`
sets bold cyan text, `yellow` sets a panel border color, and `monokai` selects
the syntax-highlighting theme used by `Syntax`.

The keys are looked up directly by `ui.py`, so keep the existing key names and
any format placeholders when changing the JSON. You can edit values to rename
the prompt, header, tool/result labels, and status messages, or change colors
and highlighting without changing the agent loop. Invalid JSON, missing keys,
or an unsupported Rich style can prevent the UI from starting.

## Running it

```sh
cd src
uv run agent.py "write a hello world script and run it"
# or: pass nothing for an interactive prompt
# or override: MODEL=openai/gpt-4o-mini OPENROUTER_API_KEY=sk-or-... uv run agent.py "..."
```

The root `pyproject.toml` declares Python 3.11+ and the project dependencies;
`uv run` installs them into the project environment when needed. The app can be
launched from `src/` as shown above, but `WORKDIR` is anchored to the repository
root, so generated files and shell commands always use root-level `work/`.
If no request is supplied on the command line, `ui.py` prompts for one and
displays the selected model name.

When run without a command-line request, the prompt starts with the active model
name, for example: `[deepseek/deepseek-v4.1-flash] Request ›`. It uses the same
model resolution as the API call: `MODEL` from the environment, then `MODEL=`
in `OPENROUTER.txt`, then the built-in fallback.

Watch the terminal: you'll see the model's text, each `tool write_file({...})`
call, the result panels, and the final response. The log makes each loop step
visible as the app runs.

## Usage metrics and tests

Each chat-completions response may include a `usage` object. `agent.py` reads
`prompt_tokens`, `completion_tokens`, and `cost` from that object: prompt and
completion tokens and cost are accumulated across model calls, while the latest
prompt-token count is used as the current context estimate. If a response omits
usage fields, the app keeps the last available values. The context limit is not
assumed; the footer shows a percentage only if the response provides
`context_limit`.

The tests live in the root `tests/` directory and use Python's standard-library
`unittest`.
They capture Rich output and replace the network call with a fixed response, so
the suite does not make an OpenRouter request or require an API key. From the
repository root, run them with the project environment:

```sh
uv run python -m unittest discover -s tests -v
```

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
