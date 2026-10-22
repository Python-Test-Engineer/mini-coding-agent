# mini-coding-agent

A small, working coding-agent demo for the AI-agents talk. It shows the core
agent loop: a model requests tools, the Python host runs them, and the results
are sent back to the model until it returns a final answer.

## What it demonstrates

- An OpenRouter chat-completions request with JSON tool schemas.
- A ReAct-style loop, limited to eight model-response steps.
- Four host tools: write, edit, and read files, plus run shell commands.
- A Rich terminal UI that displays model text, tool calls, and tool results.

The code is in `src/agent.py`; `src/ui.py` and `src/ui.json` configure the
terminal interface. `src/demo-prompt.md` contains an example request. Generated
files and commands use the repository-root `work/` directory, regardless of
where the agent is launched.

## Requirements

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- An OpenRouter API key and a model available through OpenRouter

## Configure and run

From the repository root, set the API key in PowerShell and launch the demo:

```powershell
$env:OPENROUTER_API_KEY = "your-openrouter-api-key"
cd src
uv run agent.py "write a hello world script and run it"
```

`uv run` installs the declared `rich` dependency if needed. You can also set
`OPENROUTER_API_KEY` in your environment before launching. If the key is not
set there, the app looks for an `OPENROUTER_API_KEY=` entry in the repository
root's `OPENROUTER.txt` file. Keep that file private and never commit API keys.

The model is selected from the `MODEL` environment variable, then the `MODEL=`
entry in `OPENROUTER.txt`; if neither is set, the app uses
`deepseek/deepseek-v4.1-flash`. To start without a command-line request, run:

```powershell
uv run agent.py
```

The app will prompt for a request. The agent always stores generated files in
the repository-root `work/` directory, including when launched from `src/`.

## Safety note

This is a teaching demo, not a secure sandbox. Although `work/` is the default
working directory, its file tools do not prevent paths outside that directory,
and the shell tool runs commands with the current user's permissions. Only use
trusted prompts in a controlled environment; do not expose it to untrusted
users.