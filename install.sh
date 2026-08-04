#!/usr/bin/env bash
# Install the dreaming skill for Claude Code and/or Codex CLI by symlinking
# each tool's directory in this repo into that tool's real skills directory.
# Symlinks (not copies) so `git pull` in this repo updates the installed
# skill immediately, and the repo stays the single source of truth.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

expand_config_path() {
  local path="$1"

  case "$path" in
    "~")
      path="$HOME"
      ;;
    "~/"*)
      path="$HOME/${path#\~/}"
      ;;
  esac

  path="${path//\$\{HOME\}/$HOME}"
  path="${path//\$HOME/$HOME}"

  printf '%s\n' "$path"
}

canonical_dir() {
  local path="$1"
  (cd "$path" && pwd -P)
}

CLAUDE_HOME="$(expand_config_path "${CLAUDE_CONFIG_DIR:-$HOME/.claude}")"
CODEX_HOME="$(expand_config_path "${CODEX_HOME:-$HOME/.codex}")"

INSTALL_FAILURES=()

record_failure() {
  local message="$1"
  echo "$message"
  INSTALL_FAILURES+=("$message")
}

install_one() {
  local tool="$1" src="$2" dest_dir="$3"
  local dest="$dest_dir/dreaming"

  if [ ! -d "$src" ]; then
    record_failure "$tool: source not found at $src"
    return
  fi

  mkdir -p "$dest_dir"

  if [ -L "$dest" ]; then
    local current src_real
    current="$(canonical_dir "$dest" 2>/dev/null || true)"
    src_real="$(canonical_dir "$src")"
    if [ "$current" = "$src_real" ]; then
      echo "$tool: already installed -> $dest"
      return
    fi
    echo "$tool: replacing existing symlink at $dest"
    rm "$dest"
  elif [ -e "$dest" ]; then
    record_failure "$tool: refusing to overwrite non-symlink at $dest (remove it manually first)"
    return
  fi

  ln -s "$src" "$dest"
  echo "$tool: installed $dest -> $src"
}

install_one "Claude Code" "$REPO_DIR/claude-code/dreaming" "$CLAUDE_HOME/skills"
install_one "Codex CLI"   "$REPO_DIR/codex/dreaming"       "$CODEX_HOME/skills"

echo
if [ "${#INSTALL_FAILURES[@]}" -gt 0 ]; then
  echo "Install incomplete. Resolve the following issue(s), then re-run install.sh:"
  printf ' - %s\n' "${INSTALL_FAILURES[@]}"
  exit 1
fi

echo "Done. Restart Claude Code / Codex (or start a new session) to pick up the skill."
echo "Claude Code: invoke with /dreaming [project_path] [instructions], or just ask to 'dream' about a project."
echo "Codex CLI:   ask Codex to 'dream about this project' / 'consolidate AGENTS.md' (natural-language trigger)."
