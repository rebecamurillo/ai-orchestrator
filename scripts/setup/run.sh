#!/usr/bin/env bash
# The setup runner (SPEC CAP-3, AD-28): BMAD, the client's scripts, the operator skills, the catalog, the record.
# Usage: run.sh [--reset]. Exit 0 when everything succeeded, 2 otherwise. Never touches the instance.
set -euo pipefail
export LC_NUMERIC=C

usage() { echo "usage: $0 [--reset]" >&2; exit 2; }

reset=false
case "${1:-}" in
  "") ;;
  --reset) reset=true ;;
  *) usage ;;
esac
[ "$#" -le 1 ] || usage

: "${AGENT_HOME:=/home/agent}"
: "${CLIENT_SETUP_DIR:=/client-setup}"
: "${BMAD_SCRIPT_DIR:=/bmad}"
: "${SETUP_LOG_DIR:=/logs}"
: "${OPERATOR_SKILLS_SRC:=/app/ia-agents-skills}"
: "${HARNESS_SCRIPTS_DIR:=/app/scripts/harness}"
: "${SETUP_SCRIPT_TIMEOUT:=600}"
: "${ORCH_RELEASE:=}"
if [ -z "${ORCH_SETUP_TRIGGER:-}" ]; then
  if $reset; then ORCH_SETUP_TRIGGER=reset; else ORCH_SETUP_TRIGGER=on-demand; fi
fi
case "$ORCH_SETUP_TRIGGER" in install | upgrade | on-demand | reset) ;; *) usage ;; esac
export AGENT_HOME OPERATOR_SKILLS_SRC HARNESS_SCRIPTS_DIR

COMMON="$HARNESS_SCRIPTS_DIR/_common.sh"
[ -f "$COMMON" ] || { echo "setup: $COMMON not found" >&2; exit 2; }
# shellcheck source=/dev/null
source "$COMMON"
export BMAD_VERSION

HARNESSES=(claude codex opencode)
declare -A SKILLS_DIR=()
ASSET_DIRS_ALL=()

# --- asset folders: refuse before touching anything --------------------------------------
for h in "${HARNESSES[@]}"; do
  if ! out="$("$HARNESS_SCRIPTS_DIR/$h.sh" asset-dirs 2>/dev/null)"; then
    echo "setup: $h.sh asset-dirs failed" >&2
    exit 2
  fi
  skills=()
  while IFS= read -r line; do
    case "$line" in
      "" | /* | .. | ../* | */.. | */../*)
        echo "setup: $h.sh asset-dirs printed a bad path: '$line'" >&2
        exit 2
        ;;
    esac
    ASSET_DIRS_ALL+=("$line")
    [ "$(basename "$line")" = skills ] && skills+=("$line")
  done <<<"$out"
  if [ "${#skills[@]}" -ne 1 ]; then
    echo "setup: $h.sh asset-dirs must print exactly one skills folder" >&2
    exit 2
  fi
  SKILLS_DIR[$h]="$AGENT_HOME/${skills[0]}"
done
mapfile -t ASSET_DIRS_ALL < <(printf '%s\n' "${ASSET_DIRS_ALL[@]}" | LC_ALL=C sort -u)
ASSET_PATHS=()
for d in "${ASSET_DIRS_ALL[@]}"; do
  mkdir -p "$AGENT_HOME/$d"
  ASSET_PATHS+=("$AGENT_HOME/$d")
done

ts="$(date -u +%Y%m%dT%H%M%SZ)"
at="$(date -u -d "$(printf '%s' "$ts" | sed -E 's/^(....)(..)(..)T(..)(..)(..)Z$/\1-\2-\3 \4:\5:\6/')" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)"
[ -n "$at" ] || at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
LOG="$SETUP_LOG_DIR/$ts"
mkdir -p "$LOG" "$AGENT_HOME/.orchestrator"
BMAD_JSON="$AGENT_HOME/.orchestrator/bmad.json"
overall_ok=true

# --- --reset: only children of asset folders, and bmad.json ------------------------------
if $reset; then
  for p in "${ASSET_PATHS[@]}"; do
    find "$p" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  done
  rm -f "$BMAD_JSON"
fi

# `harness<TAB>name` for every entry of bmad.json; non-zero when it cannot be read.
bmad_entries() {
  python3 - "$BMAD_JSON" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
for harness, names in (data.get("entries") or {}).items():
    for name in names:
        print(f"{harness}\t{name}")
PY
}

# --- phase 1: BMAD ------------------------------------------------------------------------
bmad_choice=installed
if [ -f "$CLIENT_SETUP_DIR/bmad.choice" ]; then
  read -r bmad_choice _ <"$CLIENT_SETUP_DIR/bmad.choice" || true
  [ -n "$bmad_choice" ] || bmad_choice=installed
fi
bmad_version=""
bmad_ok=true
bmad_reason=""
case "$bmad_choice" in
  installed)
    script="$BMAD_SCRIPT_DIR/install.sh"
    if [ ! -f "$script" ] || [ ! -x "$script" ]; then
      bmad_ok=false
      bmad_reason="bmad script not found: $script"
    else
      rc=0
      (cd "$BMAD_SCRIPT_DIR" && "$script") >"$LOG/bmad.log" 2>&1 || rc=$?
      if [ "$rc" -ne 0 ]; then
        bmad_ok=false
        bmad_reason="exit $rc"
      else
        bmad_version="$(python3 - "$BMAD_JSON" "${BMAD_VERSION:-}" <<'PY' 2>/dev/null || true
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("version") or sys.argv[2])
except Exception:
    print(sys.argv[2])
PY
)"
      fi
    fi
    ;;
  removed)
    if [ -f "$BMAD_JSON" ]; then
      if entries="$(bmad_entries 2>/dev/null)"; then
        while IFS=$'\t' read -r h name; do
          [ -n "$h" ] || continue
          if [[ "$name" == */* || "$name" == . || "$name" == .. || -z "$name" || -z "${SKILLS_DIR[$h]:-}" ]]; then
            bmad_ok=false
            bmad_reason="bad entry: $name"
            continue
          fi
          rm -rf "${SKILLS_DIR[$h]:?}/$name"
        done <<<"$entries"
        rm -f "$BMAD_JSON"
      else
        bmad_ok=false
        bmad_reason="bmad.json unreadable"
      fi
    fi
    ;;
  *)
    bmad_ok=false
    bmad_reason="unknown choice: $bmad_choice"
    ;;
esac
$bmad_ok || overall_ok=false

# --- phase 2: client scripts --------------------------------------------------------------
SCRIPTS_TSV="$(mktemp)"
trap 'rm -f "$SCRIPTS_TSV"' EXIT

entry_state() {  # $1 path
  if [ -L "$1" ]; then printf 'l:%s' "$(readlink "$1")"
  elif [ -d "$1" ]; then printf 'd:%s' "$(_dir_digest "$1")"
  elif [ -e "$1" ]; then printf 'f:%s' "$(sha256sum "$1" | cut -d' ' -f1)"
  fi
}

# Product-owned names, one per line: bmad.json entries, operator skill directories, and (per folder) bmad-*.
owned_names() {
  { bmad_entries 2>/dev/null | cut -f2 || true
    if [ -d "$OPERATOR_SKILLS_SRC" ]; then find "$OPERATOR_SKILLS_SRC" -mindepth 1 -maxdepth 1 -type d -printf '%f\n'; fi
  } | LC_ALL=C sort -u
}

candidates=()
if [ -d "$CLIENT_SETUP_DIR" ]; then
  while IFS= read -r f; do
    [ -f "$CLIENT_SETUP_DIR/$f" ] && [ -x "$CLIENT_SETUP_DIR/$f" ] && candidates+=("$f")
  done < <(find "$CLIENT_SETUP_DIR" -mindepth 1 -maxdepth 1 -name '*.sh' -printf '%f\n' | LC_ALL=C sort)
fi

for name in "${candidates[@]+"${candidates[@]}"}"; do
  slog="$LOG/$name.log"
  snap="$(mktemp -d)"
  declare -A owned=() before=()
  while IFS= read -r n; do [ -n "$n" ] && owned[$n]=1; done < <(owned_names)
  is_owned() { [[ -n "${owned[$1]:-}" || "$1" == bmad-* ]]; }
  i=0
  for p in "${ASSET_PATHS[@]}"; do
    mkdir -p "$snap/$i"
    for c in "$p"/* "$p"/.[!.]* "$p"/..?*; do
      [ -e "$c" ] || [ -L "$c" ] || continue
      n="$(basename "$c")"
      is_owned "$n" || continue
      cp -a "$c" "$snap/$i/$n"
      before["$i/$n"]="$(entry_state "$c")"
    done
    i=$((i + 1))
  done

  rc=0
  t0="$EPOCHREALTIME"
  (cd "$CLIENT_SETUP_DIR" && HOME="$AGENT_HOME" ORCH_SETUP_TRIGGER="$ORCH_SETUP_TRIGGER" \
    timeout -k 5 "$SETUP_SCRIPT_TIMEOUT" "./$name") >"$slog" 2>&1 || rc=$?
  t1="$EPOCHREALTIME"
  seconds="$(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.3f", b - a }')"

  clashes=()
  i=0
  for p in "${ASSET_PATHS[@]}"; do
    # A script may delete or replace the asset folder itself; the restore below needs it back.
    [ -d "$p" ] || { rm -f "$p"; mkdir -p "$p"; }
    declare -A seen=()
    for key in "${!before[@]}"; do
      [ "${key%%/*}" = "$i" ] && seen["${key#*/}"]=1
    done
    for c in "$p"/* "$p"/.[!.]* "$p"/..?*; do
      [ -e "$c" ] || [ -L "$c" ] || continue
      n="$(basename "$c")"
      is_owned "$n" && seen[$n]=1
    done
    for n in "${!seen[@]}"; do
      now="$(entry_state "$p/$n")"
      was="${before["$i/$n"]:-}"
      if [ "$now" != "$was" ]; then
        rm -rf "${p:?}/${n:?}"
        if [ -n "$was" ]; then cp -a "$snap/$i/$n" "$p/$n"; fi
        clashes+=("$n")
      fi
    done
    unset seen
    i=$((i + 1))
  done
  rm -rf "$snap"
  unset owned before

  clash_field=""
  if [ "${#clashes[@]}" -gt 0 ]; then
    clash_field="$(printf '%s\n' "${clashes[@]}" | LC_ALL=C sort -u | paste -sd $'\x1f' -)"
  fi
  ok=true
  { [ "$rc" -eq 0 ] && [ -z "$clash_field" ]; } || { ok=false; overall_ok=false; }
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$rc" "$ok" "$clash_field" "$seconds" "logs/setup/$ts/$name.log" >>"$SCRIPTS_TSV"
done

# --- phase 3: operator skills -------------------------------------------------------------
operator_ok=true
for h in "${HARNESSES[@]}"; do
  bash -euo pipefail -c 'source "$1"; sync_operator_skills "$2" "$3"' _ "$COMMON" "$OPERATOR_SKILLS_SRC" "${SKILLS_DIR[$h]}" \
    >>"$LOG/operator.log" 2>&1 || operator_ok=false
done
$operator_ok || overall_ok=false

# --- phase 4: catalog ---------------------------------------------------------------------
declare -A COUNT=()
for h in "${HARNESSES[@]}"; do
  COUNT[$h]=0
  [ -d "${SKILLS_DIR[$h]}" ] || { echo "$h: no skills folder" >>"$LOG/catalog.log"; continue; }
  if n="$(find "${SKILLS_DIR[$h]}" -mindepth 1 -maxdepth 1 -type d 2>>"$LOG/catalog.log" | wc -l)"; then
    COUNT[$h]=$((n))
    echo "$h: ${COUNT[$h]} skills" >>"$LOG/catalog.log"
  else
    echo "$h: skills folder unreadable" >>"$LOG/catalog.log"
    overall_ok=false
  fi
done

# --- phase 5: record ----------------------------------------------------------------------
record="$AGENT_HOME/.orchestrator/setup-run.json"
python3 - "$record.tmp.$$" "$at" "$ORCH_SETUP_TRIGGER" "$ORCH_RELEASE" "$bmad_choice" "$bmad_version" "$bmad_ok" "$bmad_reason" \
  "$operator_ok" "${COUNT[claude]}" "${COUNT[codex]}" "${COUNT[opencode]}" "$SCRIPTS_TSV" <<'PY'
import json, sys

(out, at, trigger, release, choice, version, bmad_ok, reason, operator_ok, c, x, o, tsv) = sys.argv[1:]
bmad = {"choice": choice, "version": version or None, "ok": bmad_ok == "true"}
if not bmad["ok"]:
    bmad["reason"] = reason
scripts = []
for line in open(tsv, encoding="utf-8").read().splitlines():
    name, code, ok, clashes, seconds, log = line.split("\t")
    scripts.append(
        {
            "name": name,
            "exit": int(code),
            "ok": ok == "true",
            "clashes": [c for c in clashes.split("\x1f") if c],
            "seconds": float(seconds),
            "log": log,
        }
    )
record = {
    "at": at,
    "trigger": trigger,
    "release": release,
    "bmad": bmad,
    "scripts": scripts,
    "operator": {"ok": operator_ok == "true"},
    "catalog": {"claude": int(c), "codex": int(x), "opencode": int(o)},
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(record, fh, indent=2)
    fh.write("\n")
PY
mv -f "$record.tmp.$$" "$record"

$overall_ok || exit 2
