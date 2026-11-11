#!/usr/bin/env bash
# The product's BMAD script: brings each harness to this release's BMAD and removes what an older
# version installed. Run by the setup runner; offline (BMAD ships in the image).
set -euo pipefail

: "${AGENT_HOME:=/home/agent}"
: "${HARNESS_SCRIPTS_DIR:=/app/scripts/harness}"
HARNESS_NAME=bmad
# shellcheck source=/dev/null
source "$HARNESS_SCRIPTS_DIR/_common.sh"

if [ "$#" -gt 0 ]; then
  echo "usage: $0 (no arguments)" >&2
  exit 2
fi

HARNESSES=(claude codex opencode)
declare -A TOOLS=([claude]=claude-code [codex]=codex [opencode]=opencode)
declare -A SKILLS_DIR
ALL_DIRS=()

for h in "${HARNESSES[@]}"; do
  count=0
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    case "$line" in
      /* | .. | ../* | */.. | */../*) echo "harness $h: unsafe asset dir: $line" >&2; exit 2 ;;
    esac
    ALL_DIRS+=("$line")
    if [ "${line##*/}" = skills ]; then
      SKILLS_DIR[$h]="$line"
      count=$((count + 1))
    fi
  done < <("$HARNESS_SCRIPTS_DIR/$h.sh" asset-dirs)
  if [ "$count" -ne 1 ]; then
    echo "harness $h: expected exactly one skills folder, found $count" >&2
    exit 2
  fi
done
for d in "${ALL_DIRS[@]}"; do mkdir -p "$AGENT_HOME/$d"; done

BIN="$BMAD_PREFIX/bin/bmad-method"
if [ ! -x "$BIN" ]; then
  log "bmad package not found: $BIN"
  exit 1
fi

RECORD="$AGENT_HOME/.orchestrator/bmad.json"
HAS_RECORD=false
RECORDED=""
if [ -f "$RECORD" ]; then
  HAS_RECORD=true
  if ! RECORDED="$(python3 - "$RECORD" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    entries = data["entries"]
    assert isinstance(entries, dict)
except Exception as exc:
    sys.exit(f"bmad.json unreadable: {exc}")
for harness, names in entries.items():
    if any(c in harness for c in "\t\n\r"):
        sys.exit(f"bmad.json holds an unsafe harness key: {harness!r}")
    if not isinstance(names, list):
        sys.exit(f"bmad.json entries.{harness} is not a list")
    for name in names:
        if (
            not isinstance(name, str)
            or name in ("", ".", "..")
            or any(c in name for c in "/\t\n\r")
        ):
            sys.exit(f"bmad.json holds an unsafe entry: {name!r}")
        print(f"{harness}\t{name}")
PY
  )"; then
    log "bmad.json is not usable; nothing changed"
    exit 1
  fi
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

declare -A NEW
for h in "${HARNESSES[@]}"; do
  mkdir -p "$tmp/$h"
  git -C "$tmp/$h" init -q
  if ! "$BIN" install --yes --modules bmm --tools "${TOOLS[$h]}" --directory "$tmp/$h" >&2; then
    log "bmad-method install failed for $h; nothing changed"
    exit 1
  fi
  src="$tmp/$h/.agents/skills"
  [ "$h" = claude ] && src="$tmp/$h/.claude/skills"
  if [ ! -d "$src" ]; then
    log "bmad-method install produced no $src; nothing changed"
    exit 1
  fi
  NEW[$h]="$(cd "$src" && LC_ALL=C ls -1)"
done

if $HAS_RECORD; then
  while IFS=$'\t' read -r h name; do
    [ -n "${SKILLS_DIR[$h]:-}" ] || continue
    case "$name" in "" | . | .. | */*) continue ;; esac
    rm -rf "${AGENT_HOME:?}/${SKILLS_DIR[$h]}/$name"
  done <<<"$RECORDED"
else
  for d in "${ALL_DIRS[@]}"; do
    for entry in "$AGENT_HOME/$d"/bmad-*; do
      [ -e "$entry" ] || [ -L "$entry" ] || continue
      rm -rf "$entry"
    done
  done
fi

for h in "${HARNESSES[@]}"; do
  src="$tmp/$h/.agents/skills"
  [ "$h" = claude ] && src="$tmp/$h/.claude/skills"
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    rm -rf "${AGENT_HOME:?}/${SKILLS_DIR[$h]}/$name"
    cp -R "$src/$name" "$AGENT_HOME/${SKILLS_DIR[$h]}/$name"
  done <<<"${NEW[$h]}"
done

mkdir -p "$AGENT_HOME/.orchestrator"
python3 - "$RECORD.tmp.$$" "$BMAD_VERSION" "${NEW[claude]}" "${NEW[codex]}" "${NEW[opencode]}" <<'PY'
import json, sys
out, version, *lists = sys.argv[1:]
entries = dict(zip(("claude", "codex", "opencode"), ([n for n in s.split("\n") if n] for s in lists)))
with open(out, "w") as fh:
    json.dump({"version": version, "entries": entries}, fh)
PY
mv -f "$RECORD.tmp.$$" "$RECORD"
for h in "${HARNESSES[@]}"; do
  log "$h: $(printf '%s\n' "${NEW[$h]}" | grep -c . || true) BMAD entries → ${SKILLS_DIR[$h]}"
done
