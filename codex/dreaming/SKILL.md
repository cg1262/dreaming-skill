---
name: dreaming
description: Consolidate a project's accumulated AGENTS.md memory plus its recent Codex CLI session transcripts into a new, separate AGENTS.dream.<timestamp>.md file — merging duplicate notes, replacing stale/contradicted entries, and surfacing new insights from recent sessions. Never edits the original AGENTS.md. Use when the user asks to "dream", "consolidate memory", "clean up AGENTS.md", "run a memory consolidation pass", or review/update project instructions based on recent session history.
metadata:
  short-description: Consolidate AGENTS.md + recent session history into a reviewable dream file
---

# Dreaming: memory consolidation for Codex CLI

This replicates, locally and non-destructively, the pattern behind Anthropic's
Managed Agents "dreams" feature: read the accumulated memory file plus a batch
of recent session transcripts, and synthesize a *new* file that merges,
dedupes, and updates it — without ever touching the original.

**Hard rule: never edit or delete the project's existing `AGENTS.md`.** All
output goes to a new `AGENTS.dream.<timestamp>.md` file in the same directory.
The user reviews it and decides whether to promote it manually (e.g.
`mv AGENTS.dream.20260715-140000.md AGENTS.md`) or discard it. You are not the
one who decides to promote it — never overwrite `AGENTS.md` yourself.

## Inputs

The user invokes this by asking to "dream" (optionally naming a project
directory and/or giving free-text steering), since Codex skills are triggered
from natural language, not positional slash-command arguments. Parse from
their request:

- **project directory** — if they name one, use it; otherwise use the current
  working directory.
- **free-text instructions** — optional steering for the synthesis (e.g.
  "focus on deployment gotchas, drop anything about the old auth system, keep
  it under 100 lines"). This is synthesis guidance only, not a line-editor
  command — you still exercise judgment about what belongs in the result.

## Step 1: Locate the memory file and recent transcripts (mechanical)

Run the bundled helper script — do not hand-roll this lookup:

```bash
python3 "$HOME/.codex/skills/dreaming/scripts/find_codex_project.py" "<project_dir>" --limit 8 --extract
```

(If `$CODEX_HOME` is set to something other than `~/.codex`, use
`$CODEX_HOME/skills/dreaming/scripts/find_codex_project.py` instead.)

This prints, deterministically (no synthesis):
- whether an `AGENTS.md` exists at the project root, and its path
- the Codex session rollout files (under `~/.codex/sessions/YYYY/MM/DD/`)
  whose recorded `cwd` matches the project directory, newest first — Codex
  does not group sessions by project on disk the way Claude Code does, so
  this is found by scanning rollout files' `session_meta.cwd` field
- extracted plain-text user/agent turns from each matching session (raw
  model/tool payloads and injected system instructions are stripped for
  readability)

If it reports no transcripts found, say so plainly to the user and stop —
don't fabricate history. This is expected if Codex was never launched with
this exact directory as its working directory.

If `AGENTS.md` doesn't exist yet, that's fine — synthesize purely from the
transcripts, treating the memory file as starting empty.

## Step 2: Read and synthesize (this is the actual intelligence — do this yourself, don't script it)

Read the current `AGENTS.md` in full (if present) and the extracted
transcript text from step 1. Then produce the new file's content:

1. **Merge duplicates.** If multiple notes say roughly the same thing, keep
   one clear version.
2. **Resolve staleness/contradictions in favor of the latest evidence.** If an
   existing `AGENTS.md` entry is contradicted by something in a more recent
   transcript (a preference changed, a file was renamed, a decision was
   reversed), keep the newer version and drop the outdated one. Prefer
   transcript recency over entry position in the file.
3. **Surface new insights.** Pull out durable, non-obvious facts from the
   transcripts that aren't in `AGENTS.md` yet but would help a future session
   — recurring corrections, conventions the user asserted, gotchas hit and
   fixed, decisions made and why. Skip one-off task chatter, already-derivable
   code facts, and anything that reads as "in progress" rather than settled.
4. **Preserve structure the user has already imposed** (headings, ordering,
   tone) unless it's actively getting in the way of clarity.
5. **Apply the user's free-text instructions**, if given — as emphasis/
   filtering guidance for the above, not as a literal find-replace script.
6. Keep it tight. This file gets read at the start of every future session —
   every line has an ongoing token cost. Cut anything that isn't worth that
   cost forever.

## Step 3: Write the dream file

Write the synthesized result to:

```
<project_dir>/AGENTS.dream.<YYYYMMDD-HHMMSS>.md
```

(timestamp = current local time, e.g. `AGENTS.dream.20260715-143022.md`).
Write the file directly so you can review the content before finishing. Do
**not** write to `AGENTS.md` itself.

## Step 4: Report back

Print a short summary for the user, covering:
- how many transcripts were read and over what time span
- what was merged (duplicate groups collapsed)
- what was replaced/updated as stale, and why (cite the contradicting
  transcript if relevant)
- what new insights were added
- the exact path of the new dream file
- explicit next step: *"Review `AGENTS.dream.<ts>.md`. If it looks right,
  promote it yourself with `mv <path>/AGENTS.dream.<ts>.md <path>/AGENTS.md`.
  I won't do this automatically."*
