# Change log: main → CH01 → CH02

This records the differences between the current local branch tips:

- `main` — `eab2f3b` (`add git branch guide`)
- `CH01` — `d9035da` (`test`)
- `CH02` — `43145c0` (`Create BOOK skill - rename BOOk to GUIDE`)

## Additions after the listed branch snapshots

These working-tree changes are not included in the branch-tip comparisons
above:

- Added `src/examplesCH02.py`, an API-free Rich demo of lifecycle hooks and
  allowed and rejected sandbox operations. It saves a copy of itself and a
  greeting script in `work/`, then demonstrates that a root-level
  `goodbye.py` write is rejected.
- Added `EXAMPLES/EXAMPLES.md` and a README run section with instructions for
  the demo and its standalone examples. Linked to the demo from `GUIDE/guide.html`.
- Updated the Chapter 02 file list and the combined `BOOK/book.html` page to
  include the new student examples.
- Added `SKILLS/update-docs/SKILL.md` to synchronize relevant project docs with
  code and workshop changes.
- Added a Windows `C:\Windows\Media\tada.wav` alert for sandbox policy
  rejections, including blocked writes, command syntax, and command paths.
- Added `GUIDE/agent-flow-reference.md` as a detailed logging, hooks, sandbox,
  and UI guide with an animation-ready scene outline.
- Added focused logging, hooks, sandbox, and UI animations under `GUIDE/`, with
  shared playback controls and responsive styling.
- Added `GUIDE/agent-flow.html`, an animated walkthrough of successful and
  blocked tool flows, lifecycle callbacks, sandbox checks, and direct UI calls;
  linked it from the README and workshop guide.
- Extracted the sound effects out of the source into `src/sounds.json`, keyed
  by effect name with `sound_file`, `play`, and `location`. Added `src/sounds.py`,
  which loads that catalogue and plays a named WAV when enabled. `src/lifecycle.py`
  and `src/sandbox.py` now call it instead of hard-coding the WAV paths, so a
  sound can be silenced or repointed with a config edit alone.

## Branch history note

The current `CH01` and `CH02` tips share base commit `089cf0f`; `CH02` is not a
Git descendant of the current `CH01` tip. The sections below describe direct
file-tree comparisons in the requested order, so they also call out changes
that are not cumulative across the branches.

## main → CH01

- `src/agent.py` now catches OpenRouter `HTTPError` responses and reports the
  HTTP status, selected model, and provider response body as a readable error.
- `git-missing-remote-branch.md` and three empty agent log files that exist on
  `main` are absent from `CH01`.
- The Chapter 01 harness itself is part of the branches' shared history, so it
  does not appear as a new file change in this branch-tip comparison.

## CH01 → CH02

### Lifecycle hooks and UI

- Added `src/lifecycle.py` with the `Hooks` callback contract and moved the
  lifecycle module under `src/`.
- Added an `AgentContext` and callbacks around session, input, model requests
  and responses, tool execution, loop completion, and caught errors.
- Hook failures are reported without stopping the agent loop. The UI renders
  lifecycle events, hook errors, and sandbox status.
- Added lifecycle tests for callback order, context, UI output, and failure
  isolation.

### Constrained workspace and command runner

- Added `SandboxWorkspace` to restrict writes and edits to `work/` and `logs/`.
  Relative reads use the workspace; readable absolute paths can also be read.
- Added JSONL lifecycle event logging under `logs/`.
- Added `ConstrainedLocalRunner`, which avoids the host shell, allows selected
  Python and pytest commands, runs from `work/`, and limits runtime and output.
- Added sandbox tests for path rules, event logging, command restrictions,
  limits, and agent integration.
- Updated `.gitignore`, usage metrics tests, and the README for the new behavior.

### Workshop material and repository layout

- Added `EXPLAINERS/CH02.md` and updated the workshop plan in `PLAN.md`.
- Added the combined chapter page at `EXPLAINERS/book.html`.
- Renamed `BOOK/book.html` to `GUIDE/guide.html` and updated its presentation.
- Added the `SKILLS/workshop-book/SKILL.md` guidance for maintaining the book.

## Branch-specific difference to carry forward

The current `CH02` version of `src/agent.py` calls `urlopen` directly and does
not include the OpenRouter `HTTPError` handling present on `CH01`. If `CH02` is
intended to build cumulatively on `CH01`, that behavior needs to be carried
forward in a later commit.

## Later repository layout update

- Renamed the chapter directory from `EXPLAINERS/` to `BOOK/`.
- The current chapter sources are `BOOK/CH01.md` and `BOOK/CH02.md`, and the
  current combined page is `BOOK/book.html`.
- Earlier entries retain the paths that existed when those branch changes were
  made; use the current paths for new changes.
- Removed the ignore rule for generated `logs/*.jsonl` files so CH02 audit logs
  stay visible in the checkout, matching the log files present on the CH01
  snapshot. The JSONL logging implementation was already present in CH02.

## Reader text-size controls

- Added `A−`, `A+`, and `Reset` controls above the book's right-side reading
  area.
- The controls scale chapter prose, headings, tables, and code from 80% to 160%
  in 10% steps. The TOC and controls retain their size.
- Updated `SKILLS/workshop-book/SKILL.md` with the control behavior and range.

## Follow-up conversation loop integrated from CH01

- Ported the interactive request loop from the CH01 working copy into CH02's
  agent while preserving lifecycle hooks and the constrained workspace runner.
- Shared message history and usage metrics across requests; each request keeps
  its own eight-step model/tool limit. Session hooks now wrap the conversation,
  and turn hooks still wrap each request.
- Integrated the updated `CH01.md` source into this branch and regenerated its
  section in `BOOK/book.html`; updated the guide and README to match.

## Windows session-start sound

- The base `Hooks.on_session_start()` asynchronously plays
  `%WINDIR%\Media\Windows Logon.wav` on Windows when the file is present.
- `SandboxAuditHooks` calls the base hook and still records its session-start
  event. Other platforms and unavailable audio files continue without sound.

## Forbidden writes stop the process

- A `write_file` or `edit_file` target outside repository-root `work/` and
  `logs/` is now fatal rather than a tool error the model can retry.
  `SandboxWorkspace.resolve_write_path()` prints the red `[FORBIDDEN]` banner at
  the point of detection, records a `write_forbidden` audit event, and raises
  `SandboxForbiddenError` (a `SandboxPathError` subclass). `agent_loop()` then
  raises `SystemExit(agent.FORBIDDEN_EXIT_CODE)` (status `2`) after the turn
  hooks have run.
- Fixed silent redirection into `work/`: requests such as `Desktop/notes.txt`,
  `~/Desktop/notes.txt`, `%USERPROFILE%\notes.txt`, and `Users/me/notes.txt` are
  relative on Windows, so they were previously created under `work/`. The
  resolver now expands `~` and environment variables and treats a leading
  home/system folder name as an outside request.
- `SandboxWorkspace` accepts an optional `banner` callable so tests can capture
  the message; the default prints red Rich text. `UI.show_forbidden()` was
  removed because the sandbox module now owns the announcement.
- Rejected commands and missing files still return an ordinary `ERROR: ...`
  result to the model.
- Updated `BOOK/CH02.md`, `BOOK/book.html`, `GUIDE/guide.html`, `README.md`, and
  `EXAMPLES/EXAMPLES.md`, and added tests `test_021`-`test_025` for the banner,
  the exit status, the stopped session, and home/system-relative rejection.

## Minimalist agent loop: brain, tools, and one console owner

- Split `src/agent.py` by responsibility. The system prompt, tool schemas,
  OpenRouter request, and usage totals moved to the new `src/brain.py`; the four
  tool functions and the new `bind_tools()` helper moved to the new
  `src/tools.py`. `src/agent.py` now contains only the turn context, the hook
  dispatch helpers, `agent_loop()`, and `main()`, so the ReAct cycle reads as
  one screen of code.
- `agent_loop()` binds the tool map per turn (`tools = bind_tools(context.workspace, RUNNER)`)
  so the registry and the enforcing workspace or runner cannot drift apart.
- All console output now belongs to `src/ui.py`. `UI.show_forbidden()` renders
  the red `[FORBIDDEN]` banner and `UI.show_hint()` renders the session hint,
  both from new `labels`/`styles` entries in `src/ui.json`. `src/sandbox.py`
  still detects the violation and owns the decision, but its default banner
  delegates to the UI callable instead of building a Rich console itself.
- Fixed the Windows session-start sound in `src/lifecycle.py`: the path was
  built incorrectly and named `ding.wav`, so `%WINDIR%\Media\Windows Logon.wav`
  never played. The hook now matches the documented behaviour.
- Updated the tests for the new module boundaries: `tests/test_001_agent_config.py`
  patches `brain.ROOT_DIR` and calls `brain.load_env()`, and
  `tests/test_002_agent_metrics.py` and `tests/test_005_agent_metrics.py` call
  `brain.accumulate_usage()`. `agent.chat` remains the patched network boundary
  because `agent.py` imports the function into its own namespace. All 33 tests
  pass.
- Updated the workshop material: a new "One file, one job" section, file list,
  tool-map and checklist entries in `BOOK/CH02.md` and `BOOK/book.html`; the
  module table, tool-dispatch description, and banner route in
  `GUIDE/agent-flow-reference.md` and `GUIDE/guide.html`; question 2.4 in
  `GUIDE/QUESTIONS.md`; and the file map and safety note in `README.md`.
- Updated the animations: `GUIDE/agent-flow.html` (model, tool, and ownership
  nodes, plus the normal and blocked step narrations),
  `GUIDE/sandbox-animation.html` (tool dispatch and the banner route),
  `GUIDE/ui-animation.html` (the two new display methods), and
  `GUIDE/hooks-animation.html` (hooks observe and never render).
