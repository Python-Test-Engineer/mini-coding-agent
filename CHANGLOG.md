# Change log: main → CH01 → CH02

This records the differences between the current local branch tips:

- `main` — `eab2f3b` (`add git branch guide`)
- `CH01` — `d9035da` (`test`)
- `CH02` — `43145c0` (`Create BOOK skill - rename BOOk to GUIDE`)

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
