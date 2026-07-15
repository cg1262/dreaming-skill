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

    project_dir  Project directory to inspect (default: cwd)
    --limit N    Max number of most-recent matching session transcripts (default: 5)
    --extract    Also print extracted plain-text turns from each transcript
    --codex-home Override ~/.codex (default: $CODEX_HOME or ~/.codex)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def codex_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codex"


def find_memory_file(project_dir: Path) -> Path | None:
    candidate = project_dir / "AGENTS.md"
    return candidate if candidate.is_file() else None


def session_cwd(rollout_path: Path) -> str | None:
    """Read just the first line (session_meta) to get the session's cwd."""
    try:
        with rollout_path.open(encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()
    except OSError:
        return None
    if not first_line:
        return None
    try:
        obj = json.loads(first_line)
    except json.JSONDecodeError:
        return None
    if obj.get("type") != "session_meta":
        return None
    return obj.get("payload", {}).get("cwd")


def find_matching_sessions(home: Path, project_dir: Path, limit: int) -> list[Path]:
    sessions_root = home / "sessions"
    if not sessions_root.is_dir():
        return []
    matches = []
    for rollout in sessions_root.glob("*/*/*/*.jsonl"):
        if session_cwd(rollout) == str(project_dir):
            matches.append(rollout)
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[:limit]


def extract_text(rollout_path: Path) -> str:
    """Pull plain-text user/agent turns out of a Codex rollout .jsonl.

    Uses the "event_msg" entries with type user_message/agent_message, which
    carry clean display text (as opposed to "response_item" entries, which
    include raw model/tool payloads and system-injected instructions).
    """
    lines_out = []
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
    return "\n\n".join(lines_out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--codex-home", default=None)
    args = parser.parse_args()

    project_dir = Path(args.project_dir).expanduser().resolve()
    home = Path(args.codex_home).expanduser() if args.codex_home else codex_home()

    print(f"project_dir: {project_dir}")
    print(f"codex_home: {home}")

    memory_file = find_memory_file(project_dir)
    print(f"memory_file: {memory_file if memory_file else '(none found - no AGENTS.md at project root)'}")

    sessions = find_matching_sessions(home, project_dir, args.limit)
    if not sessions:
        print("transcripts: (none found)")
        print(
            "note: no Codex session was found with cwd exactly equal to this "
            "project directory. Codex sessions are matched by the recorded "
            "cwd in each rollout file's session_meta line, since Codex (unlike "
            "Claude Code) does not group sessions into per-project directories."
        )
        return 0

    print(f"transcripts: {len(sessions)} found (most recent first)")
    for p in sessions:
        mtime = p.stat().st_mtime
        when = datetime.fromtimestamp(mtime).isoformat(sep=" ", timespec="seconds")
        print(f"  - {p} (mtime={mtime:.0f}, {when})")

    if args.extract:
        for p in sessions:
            print(f"\n===== TRANSCRIPT {p.name} =====")
            print(extract_text(p))

    return 0


if __name__ == "__main__":
    sys.exit(main())
