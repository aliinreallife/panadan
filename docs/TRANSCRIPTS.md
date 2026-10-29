# Transcript presentation — Panadan v0.4

## Scope and safety

This is a **presentation-only transformation**. Panadan never corrects, translates,
reorders, removes or edits stored Odoo transcriptions. The `Raw (متن خام)` tab
shows the exact original string as received from the reporting view; the
`Panadan formatted (نسخهٔ پانادان)` tab is a best-effort grouping by explicit
speaker markers. It is **not** a new AI-generated transcript, and ambiguous
speakers remain `نامشخص`. The original never goes to another AI service.

Supported examples:

- `اپراتور: سلام` / `مشتری: بله` on separate lines
- Standalone speaker labels followed by text on the next line
- Literal escaped `\\n` or real newline separators
- Multiline speech and speaker labels without speech
- Leading content with no speaker label, and conversations with no markers
- Trailing `\\`-continued lines (common when pasted from Markdown)

The UI initially renders up to 80 turns and can progressively display more.
It uses `textContent`, never `innerHTML`, for user transcripts.
Only users with BOTH `calls:read` and `calls:sensitive` can see the transcript
at all. The normal REST/MCP summary endpoints do not provide transcripts.

## Reading limitations

The speaker markers may come from inaccurate upstream speech-to-text.
Do not treat the visual grouping or speaker identity as verified. If the
source has no speaker markers, Panadan does not guess who spoke. Labels and
parsing warnings are always shown, and the exact raw text is one click away.

## Regression tests

`node --test tests/transcript.test.mjs`
