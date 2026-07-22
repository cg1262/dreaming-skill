#!/usr/bin/env python3
"""Atomically reserve a unique, collision-safe dream filename.

Mechanical/deterministic only: this script does not synthesize any content.
It reserves an empty file at <dir>/<base>.dream.<timestamp>.md using an
atomic exclusive-create (os.open with O_CREAT | O_EXCL) rather than a
check-then-write pattern, so two concurrent invocations targeting the same
directory and base name can never be handed the same path — there is no
window between "does this exist?" and "create it" for a second process to
land in, because the OS performs both as one syscall. If the timestamp-based
name is already taken (e.g. two runs within the same second), it
deterministically retries with an incrementing numeric suffix (-2, -3, ...)
until an atomic create succeeds. The retry loop is bounded (see
`max_attempts` below), but only as a defensive fallback against a genuine
bug (e.g. an infinite loop) — the bound is high enough that no real
same-second collision count for a single-user tool like this one could ever
reach it.

Prints the reserved (now-existing, empty) file path to stdout. The caller
is expected to then overwrite that file's contents with the actual dream
content (e.g. via the Write tool) — the file exists already only to hold
the reservation.

Usage:
    next_dream_path.py <dir> <base>

    dir   Target directory (must already exist) to reserve the file in.
    base  Base name of the memory file, without extension (e.g. "CLAUDE"
          or "AGENTS"). The reserved file is named
          <base>.dream.<YYYYMMDD-HHMMSS>.md, or
          <base>.dream.<YYYYMMDD-HHMMSS>-N.md if that timestamp is taken.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


def reserve_dream_path(directory: Path, base: str, max_attempts: int = 1_000_000) -> Path:
    """Atomically create and return a unique dream file path.

    Each candidate is created with os.open(..., O_CREAT | O_EXCL), which
    fails with FileExistsError if the path already exists — the existence
    check and the creation are a single atomic OS operation, not two
    separate steps, so there's no race window for a concurrent process to
    exploit. On collision, the next candidate is tried; this always
    terminates because each losing attempt corresponds to a distinct
    process having just won that exact path.

    max_attempts is not a realistic ceiling — it's an infinite-loop guard
    against a genuine bug in this function. Reaching a million same-second
    collisions against one directory cannot happen in normal use of a
    personal, single-user tool; if it's ever hit, something is broken (e.g.
    this function looping without actually creating files) and raising is
    the right behavior rather than spinning forever.
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for attempt in range(1, max_attempts + 1):
        suffix = "" if attempt == 1 else f"-{attempt}"
        candidate = directory / f"{base}.dream.{timestamp}{suffix}.md"
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            continue
        os.close(fd)
        return candidate
    raise RuntimeError(
        f"could not reserve a dream file path under {directory} for base "
        f"{base!r} after {max_attempts} attempts — this indicates a bug "
        f"(e.g. this loop not actually creating files), not real-world "
        f"contention"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("dir", help="Target directory to reserve the dream file in")
    parser.add_argument("base", help='Base memory file name, e.g. "CLAUDE" or "AGENTS"')
    args = parser.parse_args()

    directory = Path(args.dir).expanduser().resolve()
    if not directory.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 1

    path = reserve_dream_path(directory, args.base)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
