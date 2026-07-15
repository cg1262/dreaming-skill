#!/usr/bin/env bash
# Install the dreaming skill for Claude Code and/or Codex CLI by symlinking
# each tool's directory in this repo into that tool's real skills directory.
# Symlinks (not copies) so `git pull` in this repo updates the installed
# skill immediately, and the repo stays the single source of truth.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"

install_one() {
  local tool="$1" src="$2" dest_dir="$3"
  local dest="$dest_dir/dreaming"

  if [ ! -d "$src" ]; then
    echo "skip $tool: source not found at $src"
    return
  fi

  mkdir -p "$dest_dir"

  if [ -L "$dest" ]; then
    local current
    current="$(readlink -f "$dest")"
    if [ "$current" = "$(cd "$src" && pwd)" ]; then
      echo "$tool: already installed -> $dest"
      return
    fi
    echo "$tool: replacing existing symlink at $dest"
    rm "$dest"
  elif [ -e "$dest" ]; then
    echo "$tool: refusing to overwrite non-symlink at $dest (remove it manually first)"
    return
  fi

  ln -s "$src" "$dest"
  echo "$tool: installed $dest -> $src"
}

install_one "Claude Code" "$REPO_DIR/claude-code/dreaming" "$CLAUDE_HOME/skills"
install_one "Codex CLI"   "$REPO_DIR/codex/dreaming"       "$CODEX_HOME/skills"

echo
echo "Done. Restart Claude Code / Codex (or start a new session) to pick up the skill."
echo "Claude Code: invoke with /dreaming [project_path] [instructions], or just ask to 'dream' about a project."
echo "Codex CLI:   ask Codex to 'dream about this project' / 'consolidate AGENTS.md' (natural-language trigger)."
