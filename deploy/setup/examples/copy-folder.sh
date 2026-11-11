#!/usr/bin/env bash
# Copy the files under setup/assets/<harness>/<asset dir>/ into $HOME/<asset dir>.
# Copy this file to setup/10-copy-folder.sh and make it executable; the runner runs it.
# Each asset dir keeps `.copy-folder-installed`, the names this script copied there; an
# entry copied earlier and gone from the source is removed. A source entry replaces its
# namesake in $HOME; nothing else is touched.
set -euo pipefail

LIST=.copy-folder-installed
here="$(cd "$(dirname "$0")" && pwd)"
src="$here/assets"

if [ ! -d "$src" ]; then
  echo "copy-folder: $src not found" >&2
  exit 1
fi

# One entry per harness: the asset dirs of scripts/harness/<harness>.sh.
dirs_of() {
  case "$1" in
    claude) echo ".claude/skills .claude/agents .claude/commands" ;;
    codex) echo ".agents/skills .codex/prompts" ;;
    opencode) echo ".config/opencode/skills .config/opencode/agents .config/opencode/commands" ;;
  esac
}

sync_dir() { # $1 source dir (may be absent), $2 asset dir relative to HOME
  local from="$1" rel="$2" to="$HOME/$2" name entry
  local listfile="$to/$LIST" new="$TMP_NEW"
  : >"$new"
  if [ -d "$from" ]; then
    for entry in "$from"/* "$from"/.[!.]* "$from"/..?*; do
      [ -e "$entry" ] || [ -L "$entry" ] || continue
      name="$(basename "$entry")"
      [ "$name" != "$LIST" ] || continue
      # a newline in a name would split into a line `..` and remove the parent folder
      case "$name" in *$'\n'*) echo "copy-folder: skipped a name with a newline in $from" >&2; continue ;; esac
      printf '%s\n' "$name" >>"$new"
    done
  fi
  if [ -f "$listfile" ]; then
    while IFS= read -r name; do
      case "$name" in "" | */* | . | ..) continue ;; esac
      if ! grep -Fxq -- "$name" "$new"; then rm -rf "${to:?}/$name"; fi
    done <"$listfile"
  fi
  if [ -s "$new" ]; then
    mkdir -p "$to"
    # Listed before copying: a run stopped mid-copy still owns what it already copied.
    cp "$new" "$listfile"
    while IFS= read -r name; do
      rm -rf "${to:?}/$name"
      cp -R "$from/$name" "$to/$name"
    done <"$new"
  elif [ -f "$listfile" ]; then
    rm -f "$listfile"
  fi
}

TMP_NEW="$(mktemp)"
trap 'rm -f "$TMP_NEW"' EXIT

for harness in claude codex opencode; do
  for rel in $(dirs_of "$harness"); do
    sync_dir "$src/$harness/$rel" "$rel"
  done
done
