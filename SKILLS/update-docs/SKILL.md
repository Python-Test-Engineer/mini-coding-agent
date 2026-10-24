---
name: update-docs
description: Synchronize the Mini Coding Agent's workshop documentation with current code and requested changes, including book chapters, guides, examples, README, and changelog. Use when asked to update or reconcile project docs.
---

# Update project documentation

Use this skill to carry a code or workshop change through the documentation it
affects. Treat "update all docs" as a request to find and synchronize every
relevant document, not to rewrite unrelated material.

## Establish what changed

- Follow the user's stated scope and the active task. If the user names a
  commit, branch, chapter, or feature, use that as the source of the update.
- Otherwise inspect the working tree, staged diff, and relevant source files
  to identify the current change. If the tree is clean, use recent history
  only when the active conversation makes the intended change clear; do not
  turn a general documentation request into a rewrite of old project history.
- Keep pre-existing user edits intact. Separate them from the change being
  documented and do not overwrite them to make the documentation look clean.
- Check implementation and relevant tests before making behavior claims.

## Find and update the relevant documents

Check the current repository layout rather than assuming these paths never
change. The usual documentation areas are:

- `BOOK/CHXX.md`: canonical chapter lesson sources, kept in numeric order.
- `BOOK/book.html`: combined chapter book generated from the Markdown lessons.
- `GUIDE/guide.html` and `GUIDE/QUESTIONS.md`: guide and workshop prompts.
- `EXAMPLES/EXAMPLES.md`: runnable student examples; keep commands and code
  aligned with the current implementation.
- `README.md`: setup, run instructions, capabilities, and safety notes.
- `PLAN.md`: future work; update only when the plan itself changes.
- `CHANGLOG.md`: established changelog filename and record of completed work.

`BOOK/book.html` and `GUIDE/guide.html` are hand-maintained HTML mirrors of the
Markdown lessons; this repository has no generator for them. Mirror every
chapter or reference edit into the matching HTML section (anchors prefixed
`chapter-XX-`), keep the table of contents in step, and preserve the files'
CRLF line endings by editing them as bytes or with `newline=""`.

Update each document whose audience or instructions are affected. Keep names,
commands, paths, feature descriptions, and safety limits consistent across
them. Do not copy the same explanation everywhere when a short cross-reference
is clearer. Preserve the project's chapter sequence and its code comments for
students.

For chapter or combined-book edits, first read
`SKILLS/workshop-book/SKILL.md` in the target repository when it exists. Treat
chapter Markdown as lesson source. Discover the current HTML generation
process before rebuilding; if there is no generator, follow the local
workshop-book instructions and preserve all lesson content when updating the
combined page. Do not silently summarize chapters.

For a changelog that compares branch snapshots, first read
`SKILLS/branch-changelog/SKILL.md` in the target repository when it exists and
follow its Git ancestry, tip, and attribution checks. For an ordinary update
to completed work, add a concise factual entry to `CHANGLOG.md` using its
existing organization. Keep implementation changes distinct from
documentation-only changes. Do not create branches or tags unless the user
asks for chapter release work.

## Review the result

- Review the final diff for every changed documentation file and make sure the
  text describes current behavior rather than intended or outdated behavior.
- Check links, paths, commands, chapter order, and code examples affected by
  the update. When generated HTML changes, inspect its relevant rendered
  section and preserve the established layout.
- Do not run the application test suite for a documentation-only update unless
  the user asks. Run a documented documentation build or focused validation
  when it is needed to confirm the generated output.
- Do not commit, push, merge, or retag as part of documentation work unless
  explicitly requested.

