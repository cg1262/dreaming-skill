#!/usr/bin/env python3
"""Print a capped unified diff between a memory file and a dream file.

This is mechanical/deterministic only: it does not summarize or judge the
change. If the original memory file is missing, it diffs from an empty
baseline so first-ever dreams still get a useful review artifact.

Usage:
    dream_diff.py <original_memory_file> <dream_file> [--limit-bytes N]

    original_memory_file  CLAUDE.md / AGENTS.md path. If missing, treated as
                          an empty baseline.
    dream_file            Existing dream file to compare against.
    --limit-bytes N       Cap printed diff output (default: 20000 bytes).
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

DEFAULT_DIFF_LIMIT_BYTES = 20_000


def positive_int(value: str) -> int:
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value!r}")
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value!r}")
    return ivalue


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines(
        keepends=True
    )


def cap_text_by_bytes(text: str, limit_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit_bytes:
        return text

    prefix = encoded[:limit_bytes].decode("utf-8", errors="replace")
    return (
        prefix
        + f"\n[diff truncated: {len(encoded)} bytes total, "
        + f"showing first {limit_bytes} bytes]\n"
    )


def build_diff(original_file: Path, dream_file: Path) -> str:
    original_exists = original_file.is_file()
    original_lines = read_lines(original_file) if original_exists else []
    dream_lines = read_lines(dream_file)

    original_label = str(original_file)
    if not original_exists:
        original_label += " (missing; empty baseline)"

    return "".join(
        difflib.unified_diff(
            original_lines,
            dream_lines,
            fromfile=original_label,
            tofile=str(dream_file),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("original_memory_file")
    parser.add_argument("dream_file")
    parser.add_argument(
        "--limit-bytes", type=positive_int, default=DEFAULT_DIFF_LIMIT_BYTES
    )
    args = parser.parse_args()

    original_file = Path(args.original_memory_file).expanduser()
    dream_file = Path(args.dream_file).expanduser()

    if not dream_file.is_file():
        print(f"error: dream file not found: {dream_file}", file=sys.stderr)
        return 1
    if original_file.exists() and not original_file.is_file():
        print(
            f"error: original path exists but is not a regular file: {original_file}",
            file=sys.stderr,
        )
        return 1

    try:
        diff_text = build_diff(original_file, dream_file)
    except OSError as e:
        print(f"error: could not read input file: {e}", file=sys.stderr)
        return 1

    if not diff_text:
        print("(diff produced no output; files are identical)")
    else:
        print(cap_text_by_bytes(diff_text, args.limit_bytes), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
