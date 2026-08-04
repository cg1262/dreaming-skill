#!/usr/bin/env bash
# Promote a dream file (CLAUDE.dream.<ts>.md / AGENTS.dream.<ts>.md) into the
# real memory file it was generated from.
#
# This is the recommended way to adopt a dream's output — it backs up the
# current original first, then atomically replaces it with the dream file's
# content. It never edits the original in place and never runs on a dream
# file that doesn't exist.
#
# Usage:
#   promote_dream.sh <dream_file> [original_file]
#
#   <dream_file>     Path to the CLAUDE.dream.<ts>.md / AGENTS.dream.<ts>.md
#                     file to adopt. Must exist.
#   [original_file]  Optional explicit path to the original memory file to
#                     replace. If omitted, it's inferred from <dream_file>'s
#                     name by stripping the ".dream.<timestamp>" segment
#                     (e.g. CLAUDE.dream.20260715-143022.md -> CLAUDE.md,
#                     in the same directory). If the dream filename doesn't
#                     match that convention, pass the original path
#                     explicitly as the second argument.
#
# What it does:
#   1. Validates the dream file exists (refuses otherwise, no side effects).
#   2. Resolves the original file's path (explicit arg, or inferred).
#   3. If the original already exists, backs it up to
#      <original>.bak.<YYYYMMDD-HHMMSS> before touching anything.
#      If it doesn't exist yet, skips the backup with a warning (this is
#      the expected, valid case for a project's first-ever dream).
#   4. Atomically replaces the original with the dream file's content
#      (write a temp file in the same directory, then rename it over the
#      original — never a partial in-place write).
#   5. Prints a summary of what was backed up (if anything) and confirms
#      the original was updated.
set -euo pipefail

usage() {
  echo "Usage: $0 <dream_file> [original_file]" >&2
}

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  usage
  exit 1
fi

dream_file="$1"
explicit_original="${2:-}"

if [ ! -f "$dream_file" ]; then
  echo "error: dream file not found: $dream_file" >&2
  exit 1
fi

dream_dir="$(cd "$(dirname "$dream_file")" && pwd)"
dream_name="$(basename "$dream_file")"

if [ -n "$explicit_original" ]; then
  original_file="$explicit_original"
else
  # Infer "<name>.dream.<timestamp>.md" -> "<name>.md" in the same directory.
  if [[ "$dream_name" =~ ^(.+)\.dream\.[0-9]{8}-[0-9]{6}(-[0-9]+)?\.md$ ]]; then
    original_file="$dream_dir/${BASH_REMATCH[1]}.md"
  else
    echo "error: cannot infer the original memory file from '$dream_name'" >&2
    echo "       (expected the pattern <name>.dream.<timestamp>.md)" >&2
    echo "       pass the original path explicitly: $0 <dream_file> <original_file>" >&2
    exit 1
  fi
fi

backup_file=""
if [ -f "$original_file" ]; then
  timestamp="$(date +%Y%m%d-%H%M%S)"
  backup_file="${original_file}.bak.${timestamp}"
  # Guard against two promotions landing in the same second.
  counter=2
  while [ -e "$backup_file" ]; do
    backup_file="${original_file}.bak.${timestamp}-${counter}"
    counter=$((counter + 1))
  done
  cp -p -- "$original_file" "$backup_file"
elif [ -e "$original_file" ]; then
  echo "error: original path exists but is not a regular file: $original_file" >&2
  exit 1
else
  echo "warning: no existing original at $original_file — skipping backup (first-ever dream for this file)"
fi

# Atomic replace: write to a temp file in the same directory, then rename.
original_dir="$(cd "$(dirname "$original_file")" && pwd)"
original_name="$(basename "$original_file")"
tmp_file="$(mktemp "$original_dir/.${original_name}.promote.XXXXXX")"
cleanup() { rm -f "$tmp_file"; }
trap cleanup EXIT

cp -p -- "$dream_file" "$tmp_file"
mv -f -- "$tmp_file" "$original_file"
trap - EXIT

echo "Promoted dream file: $dream_file"
if [ -n "$backup_file" ]; then
  echo "Backed up previous original to: $backup_file"
else
  echo "No previous original existed; nothing to back up."
fi
echo "Updated original: $original_file now contains the dream file's content."
