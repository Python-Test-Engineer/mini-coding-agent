---
name: workshop-book
description: Create and maintain the Mini Coding Agent workshop chapters and their complete combined HTML book.
---

# Workshop book instructions

Use this guide when editing a chapter or building the combined book page.

## Source and content

- Treat `CHXX.md` files in this folder as the lesson source and combine them in
  filename order.
- Keep every heading, paragraph, list, table, and code block in the generated
  HTML. Add navigation and visual styling without silently summarizing or
  rewriting lesson content.
- Keep explanations appropriate for intermediate Python developers and ensure
  code examples match the implementation for that chapter.
- Preserve existing chapter text unless the request asks for content changes.
- Follow the repository's two-digit chapter naming and corresponding branch
  and tag conventions when chapter release work is requested.

## Book layout

- The preferred appearance is the current page at browser zoom 100%, matching
  the earlier appearance at 125% browser zoom. Implement the scale in the page
  CSS; do not require readers to change browser zoom.
- Keep the root font size at `125%`. Express fixed layout widths and spacing in
  `rem` so they scale with the root size. The desktop sidebar is
  `27.1875rem` (543.75px with a 16px browser default), and the article maximum
  width is `84.375rem` (1687.5px at that default).
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
