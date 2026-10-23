---
name: branch-changelog
description: Compare Git branch snapshots and write an accurate, concise changelog for this workshop repository.
---

# Branch changelog instructions

Use this skill when asked to document changes across `main` and chapter
branches, or between chapter branches.

## Compare the repository state

- Check the working tree, current branch tips, recent commits, and branch graph
  before writing. Keep uncommitted files separate from committed branch changes.
- Check merge bases and ancestry. A branch name or chapter number does not
  prove that one branch descends from another.
- Compare the requested branch tips directly and inspect relevant file diffs
  and commit summaries. Include added, changed, removed, and renamed files when
  they materially affect the story.
- Check important behavior claims against the source and tests. Call out
  branch-specific fixes that are missing from a later branch when relevant.
- Do not merge, rebase, cherry-pick, push, or retag branches merely to prepare a
  changelog.

## Write the changelog

- In this repository, the established filename is `CHANGLOG.md` (with that
  spelling). Preserve it unless the user asks to rename it.
- Organize the notes in the branch order requested by the user. Clearly state
  when that order is not the actual ancestry; describe direct branch-tip
  comparisons rather than implying changes are cumulative.
- Record the compared branch tips or commit IDs so readers know which snapshot
  the notes describe. Refresh these values each time; do not reuse stale hashes.
- Group changes by useful themes such as agent behavior, lifecycle hooks,
  sandboxing, tests, and workshop material. Prefer observable behavior over
  commit-message paraphrases.
- Keep the notes factual and distinguish implementation changes from
  documentation or repository-organization changes.

## Workshop context

- Current chapter sources and the combined book page live in `BOOK/` as
  `CHXX.md` files and `book.html`. Refer to historical paths as they existed at
  the time of the recorded change, and add a later entry when files move.
- Chapters use two-digit names such as `CH01` and `CH02`, with corresponding
  chapter branches and version tags such as `CH02-v1.0.0`.
- Treat the current `CHANGLOG.md` as the previous snapshot to update or correct
  when a later changelog is requested; verify its claims against Git again.
