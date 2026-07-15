#!/usr/bin/env python3
"""Locate a Claude Code project's memory file and recent session transcripts.

Mechanical/deterministic only: this script does not summarize, merge, or
judge staleness. It finds files and extracts plain-text turns so an agent
can read them.

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
import sys
from pathlib import Path


def claude_home() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude"


def encode_project_path(abs_path: Path) -> str:
    """Replicate Claude Code's project directory naming: '/' -> '-'."""
    return str(abs_path).replace(os.sep, "-")


def find_memory_file(project_dir: Path) -> Path | None:
    candidate = project_dir / "CLAUDE.md"
    return candidate if candidate.is_file() else None


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

    memory_file = find_memory_file(project_dir)
    print(f"memory_file: {memory_file if memory_file else '(none found - no CLAUDE.md at project root)'}")

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
        print(f"  - {p} (session {p.stem}, mtime={p.stat().st_mtime:.0f})")

    if args.extract:
        for p in transcripts:
            print(f"\n===== TRANSCRIPT {p.name} =====")
            print(extract_text(p))

    return 0


if __name__ == "__main__":
    sys.exit(main())
