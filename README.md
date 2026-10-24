# mini-coding-agent

A small, working coding-agent demo for the AI-agents talk. It shows the core
agent loop: a model requests tools, the Python host runs them, and the results
are sent back to the model until it returns a final answer.

## What it demonstrates

- An OpenRouter chat-completions request with JSON tool schemas.
- A ReAct-style loop, limited to eight model-response steps per request.
- Four host tools: contained write, edit, and read operations, plus an
  allowlisted command runner that does not start a shell.
- Lifecycle traces and sandbox audit hooks around each tool execution.
- On Windows, `%WINDIR%\Media\Windows Logon.wav` plays when a session begins,
  if the file is present. Sound effects are declared in `src/sounds.json` and
  played through `src/sounds.py`.
- A Rich terminal UI that displays model text, tool calls, and tool results.

The code is split by responsibility. `src/agent.py` is the loop: it owns the
turn context, the hook calls, and the model/tool cycle. `src/brain.py` holds the
system prompt, the tool schemas, and the OpenRouter request. `src/tools.py`
holds the four tool functions and `bind_tools()`, which attaches the enforcing
workspace or runner. `src/sandbox.py` contains the path and command policy,
`src/lifecycle.py` the callback contract, and `src/agent_logging.py` the JSONL
audit trail. `src/ui.py` and `src/ui.json` own every line the program prints.
`src/demo-prompt.md` contains an example request. Generated files and commands
use the repository-root `work/` directory, regardless of where the agent is
launched. Lifecycle and sandbox records are written as JSONL files under
repository-root `logs/`.

See the [animated agent flow explainer](GUIDE/agent-flow.html) for the request,
hook, sandbox, and UI event paths.
See the [flow reference and animation storyboard](GUIDE/agent-flow-reference.md)
for the detailed event sequence and component responsibilities.
The focused [logging](GUIDE/logging-animation.html), [hooks](GUIDE/hooks-animation.html),
[sandbox](GUIDE/sandbox-animation.html), and [UI](GUIDE/ui-animation.html) animations
walk through each feature separately.

## Run the offline hook and sandbox examples

The API-free Rich demo shows lifecycle callbacks and sandbox operations that
pass or fail as expected. From the repository root, run:

```powershell
cd src
uv run python examplesCH02.py
```

The demo copies itself and a greeting script into `work/`, then shows that a
write to the repository root is rejected. See [EXAMPLES/EXAMPLES.md](EXAMPLES/EXAMPLES.md)
for the walkthrough and standalone snippets.

## Requirements

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- An OpenRouter API key and a model available through OpenRouter

## Configure and run

Add the following settings to the repository-root `.env` file (the file is
ignored by Git):

```dotenv
OPENROUTER_API_KEY=your-openrouter-api-key
MODEL=deepseek/deepseek-v4.1-flash
```

Then launch the demo from the repository root:

```powershell
cd src
uv run agent.py "write a hello world script and run it"
```

`uv run` installs the project dependencies if needed. Shell environment
variables override values in `.env`. Keep credentials private and never commit
the `.env` file.

If `MODEL` is omitted from both the environment and `.env`, the app uses
`deepseek/deepseek-v4.1-flash`. To start without a command-line request, run:

```powershell
uv run agent.py
```

The app prompts for a request if you did not provide one on the command line.
After each answer, it asks for another request and keeps the conversation
history. Type `exit` or `quit` to finish. The agent always stores generated
files in the repository-root `work/` directory, including when launched from
`src/`. It appends one JSON object per lifecycle event to a generated file in
`logs/`.

## Safety note

This is a teaching demo with a **constrained local runner**, not a strong
operating-system sandbox. The file tools can read any readable absolute path,
but reject write/edit targets outside repository-root `work/` and `logs/`.
`SandboxWorkspace.resolve_write_path()` is where that rule is decided: it
expands `~` and environment variables, then refuses anything outside the two
roots. Home- and system-relative requests count as outside, so `Desktop/notes.txt`,
`~/Desktop/notes.txt`, and `%USERPROFILE%\notes.txt` are rejected instead of
being created under `work/`. A blocked write or edit is fatal: the sandbox asks
`UI.show_forbidden()` for a red `[FORBIDDEN]` banner (wording and colour in
`src/ui.json`) and exits with status `2` (`agent.FORBIDDEN_EXIT_CODE`)
instead of letting the model retry the same request with another path. On
Windows, sandbox policy violations play `C:\Windows\Media\tada.wav`; rejected
commands are still returned to the model as normal `ERROR: ...` results.
The runner uses `shell=False`, an allowlist (`python` and `pytest` variants), a
timeout, bounded output, and rejects parent/absolute command paths. Its child
processes still run with the current user's permissions and are not
network-isolated; a Python script could deliberately bypass the host file-tool
policy. Only use trusted prompts in a controlled environment. Use a container
or VM runtime before exposing the agent to untrusted users.
