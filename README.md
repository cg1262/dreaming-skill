# dreaming-skill

A personal, cross-tool "dreaming" memory-consolidation skill for **Claude Code**
and **Codex CLI**.

## What this is

Anthropic's Managed Agents product has a research-preview feature called
"dreams": periodically, a background pass reads an agent's accumulated memory
plus recent session history and produces a consolidated update — merging
duplicate notes, dropping stale/contradicted entries, and folding in new
insights.

This repo replicates that *pattern* locally, using tools already on this
machine, for the two memory files these CLIs actually maintain:

| Tool         | Memory file  | Skill location (after install)  |
|--------------|--------------|----------------------------------|
| Claude Code  | `CLAUDE.md`  | `~/.claude/skills/dreaming/`     |
| Codex CLI    | `AGENTS.md`  | `~/.codex/skills/dreaming/`      |

### How it differs from the real "dreams" feature

- **Not the same feature, not calling that API.** This is a locally-run
  skill/prompt, invoked manually (or via a slash command / natural-language
  request), not a managed background job running on Anthropic's
  infrastructure.
- **Never touches the original memory file.** The real dreams feature (per
  its research-preview description) also produces a proposal for review, but
  here that's an absolute, hard-coded rule: the skill is instructed to never
  write to `CLAUDE.md`/`AGENTS.md`, only to a new
  `CLAUDE.dream.<timestamp>.md` / `AGENTS.dream.<timestamp>.md` file. You
  promote it yourself (`mv CLAUDE.dream.<ts>.md CLAUDE.md`) or delete it.
- **The dream filename is reserved atomically, not just picked by the
  model.** Choosing *which* new filename to write to is a small deterministic
  script (`next_dream_path.py`), not a check-then-write prompt instruction —
  see [Mechanism notes](#mechanism-notes) for exactly what guarantee that
  does and doesn't provide.
- **The synthesis is done by whichever agent runs the skill** (Claude Code or
  Codex, using their normal model + normal judgment) — reading the SKILL.md's
  instructions like any other skill. There's no separate dedicated model or
  hosted pipeline behind this.
- **The "locate transcripts" step is a small deterministic script**, not a
  model call — see [Mechanism notes](#mechanism-notes) for why, and exactly
  what it does and doesn't do.

## Repo layout

```
dreaming-skill/
├── README.md
├── install.sh                       # symlinks the two skill dirs into place
├── scripts/
│   ├── find_claude_project.py       # locate CLAUDE.md + recent transcripts
│   ├── find_codex_project.py        # locate AGENTS.md + recent transcripts
│   └── next_dream_path.py           # atomically reserve a unique dream filename
├── claude-code/
│   └── dreaming/
│       ├── SKILL.md                 # -> ~/.claude/skills/dreaming/SKILL.md
│       └── scripts -> ../../scripts  (symlink)
└── codex/
    └── dreaming/
        ├── SKILL.md                 # -> ~/.codex/skills/dreaming/SKILL.md
        └── scripts -> ../../scripts  (symlink)
```

Both `SKILL.md` files reference the same three helper scripts (via a symlink
into the shared `scripts/` directory) so there's one implementation of the
mechanical lookup and filename-reservation logic, not two copies to keep in
sync.

## Install

```bash
git clone <this repo, or just use it in place at> ~/dreaming-skill
~/dreaming-skill/install.sh
```

This symlinks:
- `~/dreaming-skill/claude-code/dreaming` → `~/.claude/skills/dreaming`
- `~/dreaming-skill/codex/dreaming` → `~/.codex/skills/dreaming`

It's safe to re-run (idempotent) and respects `$CLAUDE_CONFIG_DIR` /
`$CODEX_HOME` if you've customized those. Start a new Claude Code / Codex
session afterward to pick up the skill (both tools auto-discover skills from
their skills directory; Claude Code even picks up changes mid-session).

To uninstall: delete the two symlinks (`rm ~/.claude/skills/dreaming
~/.codex/skills/dreaming`); nothing else on your system is touched.

## Usage

### Claude Code

```
/dreaming
/dreaming ~/some-project
/dreaming ~/some-project "focus on deployment gotchas, drop anything about the old auth system"
```

Or just ask in plain language — the skill's description is written so Claude
Code can trigger it automatically for requests like "dream about this
project" or "consolidate CLAUDE.md based on recent sessions". `argument-hint`
and a declared `arguments: [project_path, instructions]` list give it
`$project_path` / `$instructions` when invoked as a slash command; both are
optional (defaults: current directory, no special steering).

Example output:
```
transcripts: 6 found spanning 2026-07-02 to 2026-07-15
Merged: 3 duplicate notes about the Netlify build step into one.
Replaced: "uses npm" -> "uses pnpm" (contradicted in the 2026-07-11 session
  where the build was migrated).
Added: "OG images are generated at build time via Satori, not client-side."
Wrote: /home/cgamb/gambill-data-website/CLAUDE.dream.20260715-143022.md

Review it, then promote manually if it looks right:
  mv CLAUDE.dream.20260715-143022.md CLAUDE.md
```

### Codex CLI

Codex skills trigger from natural language, not slash-command positional
arguments (Codex has no equivalent of Claude Code's `$ARGUMENTS`/`arguments:`
frontmatter — see [Mechanism notes](#mechanism-notes)). Just ask:

```
codex "dream about ~/some-project, focus on deployment gotchas"
```

or, from within the project directory, interactively:
```
$ cd ~/some-project && codex
> dream about this project
```

Codex will read the skill's description, trigger it, run the same helper
script, synthesize, and write `AGENTS.dream.<timestamp>.md` — never touching
`AGENTS.md`.

## Mechanism notes

These are the real extension points this skill relies on, confirmed by
inspecting this machine and Claude Code's own docs (not assumed):

- **Claude Code personal skills** live at `~/.claude/skills/<name>/SKILL.md`
  (or a project's `.claude/skills/`), auto-discovered with no registration
  step. Frontmatter fields Claude Code actually parses: `name`, `description`,
  `when_to_use`, `argument-hint`, `arguments`, `disable-model-invocation`,
  `user-invocable`, `allowed-tools`, `disallowed-tools`, `model`, `effort`,
  `context`, `agent`, `hooks`, `paths`, `shell`. Arguments are passed as
  `$ARGUMENTS` (whole string), `$0`/`$1`/... (positional), or `$name` for each
  entry declared in a frontmatter `arguments:` list — this skill uses the
  latter (`arguments: [project_path, instructions]`). Bundled `scripts/` /
  `references/` directories are a real, standard convention.

- **Claude Code session transcripts** live at
  `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`, one directory per
  project, one JSONL file per session. `<encoded-cwd>` is the project's
  absolute path with every `/` replaced by `-` (e.g. `/home/cgamb/foo` →
  `-home-cgamb-foo`) — confirmed empirically on this machine (not documented
  publicly as far as I could verify, so `find_claude_project.py` fails
  loudly rather than guessing further if the computed directory doesn't
  exist). Each line is a JSON event; `type: "user"` / `type: "assistant"`
  lines carry the actual conversation (`message.content`, either a plain
  string or a list of typed blocks — `text`, `tool_use`, `tool_result`,
  `thinking`); `isSidechain: true` marks subagent-internal turns, which the
  helper script skips.

- **Codex CLI has a real, first-class skill mechanism** at
  `$CODEX_HOME/skills/<name>/SKILL.md` (`~/.codex/skills` by default) — the
  *same* SKILL.md convention as Claude Code / the Claude API's Agent Skills
  (`name` + `description` frontmatter only; optional `metadata.
  short-description`; optional `scripts/`, `references/`, `assets/`,
  `agents/` subdirectories). This machine already ships built-in examples
  under `~/.codex/skills/.system/` (`skill-creator`, `skill-installer`,
  `plugin-creator`, `imagegen`, `openai-docs`), which is how this convention
  was confirmed rather than assumed. Unlike Claude Code, Codex skills are
  triggered purely by matching the natural-language request against
  `description` — there's no slash-command positional-argument system, so
  this skill's Codex `SKILL.md` tells the agent to parse the project
  directory and instructions out of the user's own words instead.

- **Codex CLI session transcripts** live at
  `~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<uuid>.jsonl` — one
  file per session, *not* grouped by project on disk. Each rollout's first
  line is a `session_meta` event whose `payload.cwd` records the working
  directory the session started from, so `find_codex_project.py` finds "this
  project's" sessions by scanning all rollout files and filtering on that
  field. Within a rollout, `event_msg` lines with `payload.type ==
  "user_message"` / `"agent_message"` carry clean display text; `response_item`
  lines carry the raw model/tool payloads (including injected system
  instructions) that the helper script deliberately skips.

- **The dream filename is reserved with an atomic exclusive-create, not a
  check-then-write.** `next_dream_path.py` picks a candidate name
  (`<base>.dream.<YYYYMMDD-HHMMSS>.md`) and creates it via
  `os.open(path, os.O_CREAT | os.O_EXCL)` — existence-check and creation are
  a single OS syscall, so there is no window in which a second, concurrent
  invocation could observe the same name as free. If the create fails
  because the name is taken (e.g. two dreams launched in the same second),
  it retries with an incrementing suffix (`-2`, `-3`, ...) until an atomic
  create succeeds, so two simultaneous runs against the same directory are
  guaranteed distinct filenames — this is an actual guarantee enforced by
  the OS, not a "please check first" instruction to the model. This closes
  a gap flagged in review: filename selection used to be prompt-only
  (`SKILL.md` telling the model to check for an existing dream file and
  pick another name), which was a check-then-write race, not an atomic one.

## Limitations / things to know

- `find_claude_project.py` and `find_codex_project.py` are read-only and
  mechanical: they locate files and strip transcripts down to plain
  conversational text. `next_dream_path.py` has exactly one side effect — it
  creates the single empty file whose path it prints, to hold its atomic
  reservation. None of the three scripts do any summarization: all actual
  judgment (merging, staleness resolution, what counts as a durable insight)
  is done by the invoking agent per the SKILL.md instructions — there is no
  standalone "dream" model or algorithm here.
- Claude Code's project-directory encoding (`/` → `-`) was reverse-engineered
  from this machine's actual `~/.claude/projects/` layout, not from public
  docs — if a project path itself happens to contain a literal `-` where a
  `/` also got substituted, the mapping is not perfectly invertible, but the
  forward direction (path → directory name) used here is unambiguous and is
  what matters for lookup.
- On this machine, most Claude Code sessions were run with the process's cwd
  set to the home directory rather than to the specific project subfolder
  being worked on — so a given project subdirectory may show "no transcripts
  found" even though real work happened on it, simply because Claude Code
  wasn't *launched* from inside that directory. This is a property of how
  Claude Code keys history (by launch cwd), not a bug in these scripts.
- Codex history on this machine is minimal (one trivial session at the time
  of writing), so the Codex path is validated for correct wiring
  (locates `AGENTS.md`, locates/filters sessions by `cwd`, extracts clean
  text) rather than against a rich multi-session real-world transcript set.
