#!/usr/bin/env python3
"""Locate a Claude Code project's memory file(s) and recent session transcripts.

Mechanical/deterministic only: this script does not summarize, merge, or
judge staleness. It finds files and extracts plain-text turns so an agent
can read them.

Claude Code loads both CLAUDE.md and AGENTS.md at a project root as memory, so
this reports whichever of the two exist (many repos keep their agent
instructions in AGENTS.md and have no CLAUDE.md).

Claude Code stores per-project session transcripts under:
    ~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl
where <encoded-cwd> is the project's absolute path with every "/" replaced
by "-" (e.g. /home/cgamb/foo -> -home-cgamb-foo). This encoding was
confirmed empirically on this machine, not from public docs, so if the
computed directory doesn't exist, this script says so plainly rather than
guessing further.

Usage:
    find_claude_project.py [project_dir] [--limit N] [--extract] [--claude-home DIR]

    project_dir   Project directory to inspect (default: cwd)
    --limit N     Max number of most-recent session transcripts to include (default: 5)
    --extract     Also print extracted plain-text turns from each transcript
    --claude-home Override ~/.claude (default: $CLAUDE_CONFIG_DIR or ~/.claude)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


def claude_home() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude"


def encode_project_path(abs_path: Path) -> str:
    """Replicate Claude Code's project directory naming.

    Claude Code sanitizes the absolute cwd into a single directory name by
    replacing every character that isn't alphanumeric with '-'. In practice
    that means both the path separator '/' and '.' (e.g. in a username like
    'scott.haines') become '-': /Users/scott.haines/foo ->
    -Users-scott-haines-foo. Confirmed empirically on this machine.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", str(abs_path))


# Agent-memory files Claude Code reads at a project root, in preference order.
# Claude Code loads both CLAUDE.md and AGENTS.md as project memory, so a project
# may use either or both; many repos keep their agent instructions in AGENTS.md
# and have no CLAUDE.md at all.
MEMORY_FILENAMES = ("CLAUDE.md", "AGENTS.md")


def find_memory_files(project_dir: Path) -> list[Path]:
    """Return the agent-memory files present at the project root, if any.

    Looks for both CLAUDE.md and AGENTS.md (in that order) so the skill can
    consolidate whichever one(s) a project actually maintains.
    """
    return [
        candidate
        for name in MEMORY_FILENAMES
        if (candidate := project_dir / name).is_file()
    ]


def list_transcripts(project_transcript_dir: Path, limit: int) -> list[Path]:
    if not project_transcript_dir.is_dir():
        return []
    jsonl_files = [p for p in project_transcript_dir.glob("*.jsonl") if p.is_file()]
    jsonl_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return jsonl_files[:limit]


def extract_text(transcript_path: Path) -> str:
    """Pull plain-text user/assistant turns out of a Claude Code .jsonl transcript.

    Skips sidechain (subagent) turns and non-text content blocks (tool_use,
    tool_result, thinking) to keep output readable. This is raw extraction,
    not summarization.
    """
    lines_out = []
    with transcript_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") not in ("user", "assistant"):
                continue
            if obj.get("isSidechain"):
                continue
            message = obj.get("message") or {}
            role = message.get("role", obj.get("type"))
            content = message.get("content")
            text_parts = []
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            text_parts.append(text)
            if text_parts:
                lines_out.append(f"[{role}]\n" + "\n".join(text_parts))
    return "\n\n".join(lines_out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--claude-home", default=None)
    args = parser.parse_args()

    project_dir = Path(args.project_dir).expanduser().resolve()
    home = Path(args.claude_home).expanduser() if args.claude_home else claude_home()
    encoded = encode_project_path(project_dir)
    project_transcript_dir = home / "projects" / encoded

    print(f"project_dir: {project_dir}")
    print(f"claude_home: {home}")
    print(f"encoded_project_dir: {project_transcript_dir}")

    memory_files = find_memory_files(project_dir)
    if memory_files:
        for mf in memory_files:
            print(f"memory_file: {mf}")
    else:
        print("memory_file: (none found - no CLAUDE.md or AGENTS.md at project root)")

    transcripts = list_transcripts(project_transcript_dir, args.limit)
    if not transcripts:
        print("transcripts: (none found)")
        print(
            "note: no Claude Code session history is recorded for this exact "
            "project directory. This happens if Claude Code was never launched "
            "with this directory as its working directory (history is keyed by "
            "the process cwd at session start, not by files touched during the "
            "session)."
        )
        return 0

    print(f"transcripts: {len(transcripts)} found (most recent first)")
    for p in transcripts:
        mtime = p.stat().st_mtime
        when = datetime.fromtimestamp(mtime).isoformat(sep=" ", timespec="seconds")
        print(f"  - {p} (session {p.stem}, mtime={mtime:.0f}, {when})")

    if args.extract:
        for p in transcripts:
            print(f"\n===== TRANSCRIPT {p.name} =====")
            print(extract_text(p))

    return 0


if __name__ == "__main__":
    sys.exit(main())
