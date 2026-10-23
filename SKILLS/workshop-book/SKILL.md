---
name: workshop-book
description: Create and maintain the Mini Coding Agent workshop chapters and their complete combined HTML book.
---

# Workshop book instructions

Use this guide when editing a chapter or building the combined book page.

## Source and content

- Treat `BOOK/CHXX.md` files as the lesson source and combine them in filename
  order.
- Include only chapter files present on the current branch. When a later
  chapter is absent, remove it from the generated page rather than carrying
  stale chapter content forward from an earlier HTML build.
- Keep every heading, paragraph, list, table, and code block in the generated
  HTML. Add navigation and visual styling without silently summarizing or
  rewriting lesson content.
- Keep explanations appropriate for intermediate Python developers and ensure
  code examples match the implementation for that chapter.
- Preserve existing chapter text unless the request asks for content changes.
- For readability edits, aim for 15–20 words per sentence. Split sentences over
  25 words where this reads naturally, while preserving every fact, caveat, and
  relationship. Do not shorten code, tables, checklists, or examples.
- Follow the repository's two-digit chapter naming and corresponding branch
  and tag conventions when chapter release work is requested.

## Book layout

- The preferred appearance is the current page at browser zoom 100%, matching
  the earlier appearance at 125% browser zoom. Implement the scale in the page
  CSS; do not require readers to change browser zoom.
- Keep the root font size at `125%`. Express fixed spacing in `rem` so it
  scales with the root size.
- On desktop, make the left table-of-contents column `25%` of the page width.
  Set this using the `--toc-width` CSS custom property in `:root`, and use that
  variable for the grid's first column. To change the proportion, edit that
  one value (for example, `20%` or `30%`).
- Let the chapter column use the remaining width, with a readable maximum
  content width of `84.375rem` (1687.5px with a 16px browser default and the
  125% root font size).
- Add accessible right-side reading controls in this order: `Text size`, `A−`,
  a live percentage, `A+`, and `Reset`. Keep their appearance and order aligned
  with the CH02 branch controls. Scale prose, headings, tables, and code without
  changing the TOC or controls. Default to 100%; provide 80% to 160% sizing in
  10% steps, with disabled buttons at the limits.
- Scale the responsive breakpoint with the layout. The single-column layout
  begins at `1025px`, corresponding to the previous `820px` breakpoint at
  125% browser zoom.
- Keep the table of contents on the left on wide screens and retain a readable
  single-column layout on smaller screens. Section links must point to the
  matching chapter headings.
- Keep code blocks horizontally scrollable and comfortably readable.

## Agent and sandbox explanations

- The host application enforces file and command restrictions where those
  actions execute. Lifecycle hooks can observe or extend behavior, but are not
  a security boundary by themselves.
- Describe constrained local process execution accurately; do not call it an
  operating-system sandbox or container unless the implementation provides one.

## Review

- After changing the combined page, inspect it at browser zoom 100% and check
  the table of contents, chapter links, code blocks, and narrow-screen layout.
- When changing application behavior, keep relevant tests and chapter
  explanations aligned with the implementation.
