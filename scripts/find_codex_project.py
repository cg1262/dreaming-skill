#!/usr/bin/env python3
"""Locate a Codex CLI project's memory file and recent session transcripts.

Mechanical/deterministic only: this script does not summarize, merge, or
judge staleness. It finds files and extracts plain-text turns so an agent
can read them.

Unlike Claude Code, Codex does not encode the project path into a directory
name. Session rollouts are stored at:
    ~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<uuid>.jsonl
with no project grouping on disk. Each rollout's first line is a
"session_meta" event whose payload.cwd records the working directory the
session was started from. So finding "this project's" sessions means
scanning all rollout files and filtering by that cwd field (confirmed by
inspecting a real rollout file on this machine).

Usage:
    find_codex_project.py [project_dir] [--limit N] [--extract] [--codex-home DIR]
                           [--max-chars-per-file N] [--max-total-chars N]

    project_dir           Project directory to inspect (default: cwd)
    --limit N             Max number of most-recent matching session
                           transcripts (default: 5, must be a positive integer)
    --extract             Also print extracted plain-text turns from each
                           transcript
    --codex-home DIR      Override ~/.codex (default: $CODEX_HOME or ~/.codex)
    --max-chars-per-file  Cap on extracted characters per transcript, after
                           which the rest of that file is replaced with a
                           truncation marker (default: 50000)
    --max-total-chars     Cap on total extracted characters across all
                           transcripts combined (default: 200000)

Rollout files that can't be read or parsed are no longer silently treated
the same as "doesn't belong to this project": they're reported as skipped
so the user can tell "zero history" apart from "some history was skipped
due to an error". Unreadable transcript files during extraction likewise
degrade to a "[unreadable: ...]" placeholder instead of crashing the run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_MAX_CHARS_PER_FILE = 50_000
DEFAULT_MAX_TOTAL_CHARS = 200_000


def positive_int(value: str) -> int:
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value!r}")
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value!r}")
    return ivalue


def codex_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codex"


def find_memory_file(project_dir: Path) -> Path | None:
    candidate = project_dir / "AGENTS.md"
    return candidate if candidate.is_file() else None


def session_cwd(rollout_path: Path) -> tuple[str | None, str | None]:
    """Read just the first line (session_meta) to get the session's cwd.

    Returns (cwd, error). `error` is set only when the file itself couldn't
    be read or its first line couldn't be parsed as JSON — i.e. a real
    failure, distinct from `cwd` legitimately being None/absent because the
    first line simply isn't a session_meta event (which is not an error, just
    a non-match).
    """
    try:
        with rollout_path.open(encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()
    except OSError as e:
        return None, f"{rollout_path}: {e}"
    if not first_line:
        return None, None
    try:
        obj = json.loads(first_line)
    except json.JSONDecodeError as e:
        return None, f"{rollout_path}: invalid JSON in first line ({e})"
    if obj.get("type") != "session_meta":
        return None, None
    return obj.get("payload", {}).get("cwd"), None


def find_matching_sessions(
    home: Path, project_dir: Path, limit: int
) -> tuple[list[Path], list[str]]:
    sessions_root = home / "sessions"
    if not sessions_root.is_dir():
        return [], []
    matches = []
    errors = []
    for rollout in sessions_root.glob("*/*/*/*.jsonl"):
        cwd, error = session_cwd(rollout)
        if error:
            errors.append(error)
            continue
        if cwd == str(project_dir):
            matches.append(rollout)
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[:limit], errors


def truncate_text(text: str, max_chars: int | None) -> str:
    if max_chars is None or len(text) <= max_chars:
        return text
    truncated_chars = len(text) - max_chars
    return text[:max_chars] + f"\n\n[... {truncated_chars} characters truncated ...]"


def extract_text(rollout_path: Path, max_chars: int | None = None) -> str:
    """Pull plain-text user/agent turns out of a Codex rollout .jsonl.

    Uses the "event_msg" entries with type user_message/agent_message, which
    carry clean display text (as opposed to "response_item" entries, which
    include raw model/tool payloads and system-injected instructions).

    If the file can't be opened or read (permission error, deleted mid-read,
    etc.) this returns a placeholder string describing the failure instead of
    raising, so one bad transcript doesn't abort extraction of the rest.
    """
    lines_out: list[str] = []
    try:
        with rollout_path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "event_msg":
                    continue
                payload = obj.get("payload", {})
                kind = payload.get("type")
                if kind == "user_message":
                    text = payload.get("message", "")
                    if text:
                        lines_out.append(f"[user]\n{text}")
                elif kind == "agent_message":
                    text = payload.get("message", "")
                    if text:
                        lines_out.append(f"[assistant]\n{text}")
    except OSError as e:
        return f"[unreadable: {rollout_path} — {e}]"

    text = "\n\n".join(lines_out)
    return truncate_text(text, max_chars)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--limit", type=positive_int, default=5)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--codex-home", default=None)
    parser.add_argument(
        "--max-chars-per-file", type=positive_int, default=DEFAULT_MAX_CHARS_PER_FILE
    )
    parser.add_argument(
        "--max-total-chars", type=positive_int, default=DEFAULT_MAX_TOTAL_CHARS
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).expanduser().resolve()
    home = Path(args.codex_home).expanduser() if args.codex_home else codex_home()

    print(f"project_dir: {project_dir}")
    print(f"codex_home: {home}")

    memory_file = find_memory_file(project_dir)
    print(f"memory_file: {memory_file if memory_file else '(none found - no AGENTS.md at project root)'}")

    sessions, errors = find_matching_sessions(home, project_dir, args.limit)

    if errors:
        for err in errors:
            print(f"warning: could not read/parse session file: {err}", file=sys.stderr)

    if not sessions:
        print("transcripts: (none found)")
        if errors:
            print(
                f"note: {len(errors)} session file(s) could not be read or parsed "
                "and were skipped (see warnings above). This is different from "
                "there being no history at all — some session(s) may belong to "
                "this project but couldn't be checked."
            )
        else:
            print(
                "note: no Codex session was found with cwd exactly equal to this "
                "project directory. Codex sessions are matched by the recorded "
                "cwd in each rollout file's session_meta line, since Codex (unlike "
                "Claude Code) does not group sessions into per-project directories."
            )
        return 0

    print(f"transcripts: {len(sessions)} found (most recent first)")
    if errors:
        print(
            f"note: {len(errors)} additional session file(s) could not be read or "
            "parsed and were skipped (see warnings above); they may or may not "
            "have belonged to this project."
        )
    for p in sessions:
        mtime = p.stat().st_mtime
        when = datetime.fromtimestamp(mtime).isoformat(sep=" ", timespec="seconds")
        print(f"  - {p} (mtime={mtime:.0f}, {when})")

    if args.extract:
        remaining_total = args.max_total_chars
        for p in sessions:
            print(f"\n===== TRANSCRIPT {p.name} =====")
            if remaining_total <= 0:
                print(
                    "[... total output budget exhausted; remaining transcripts "
                    "skipped ...]"
                )
                continue
            per_file_cap = min(args.max_chars_per_file, remaining_total)
            text = extract_text(p, per_file_cap)
            print(text)
            remaining_total -= len(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
