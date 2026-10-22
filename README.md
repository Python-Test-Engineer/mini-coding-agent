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

The app will prompt for a request. The agent always stores generated files in
the repository-root `work/` directory, including when launched from `src/`.

## Safety note

This is a teaching demo, not a secure sandbox. Although `work/` is the default
working directory, its file tools do not prevent paths outside that directory,
and the shell tool runs commands with the current user's permissions. Only use
trusted prompts in a controlled environment; do not expose it to untrusted
users.