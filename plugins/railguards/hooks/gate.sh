#!/usr/bin/env bash
# Runner of the railguards gate. The judgement half lives in skills/gate; checks live in checks/*.sh.
#   gate.sh status                                    run every check, show the report and the approval state
#   gate.sh approve --checks "<run>" [--confirmed "<what the developer confirmed>"]
#   gate.sh hook                                      PreToolUse hook: reads the tool call JSON on stdin
# A check is an executable script in <plugin>/checks or <project>/.claude/checks. See the plugin README.

SELF="${BASH_SOURCE[0]}"
PLUGIN="$(cd "$(dirname "$SELF")/.." && pwd)"
export RG_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
cd "$RG_ROOT" || exit 0
. "$PLUGIN/lib/conf.sh"
STATE="$RG_ROOT/.claude/.railguards"

collect() {
  git rev-parse --verify -q "origin/$RG_BASE" >/dev/null || { echo "origin/$RG_BASE not found. Run: git fetch origin $RG_BASE" >&2; return 2; }
  RG_MB=$(git merge-base "origin/$RG_BASE" HEAD) || return 2
  export RG_BASE RG_MB
  FP=$(git diff --no-renames "$RG_MB" HEAD | shasum | cut -c1-16)
  FLAGGED="" CHECKS_REPORT=""
  local f name out rc
  for f in "$PLUGIN"/checks/*.sh "$RG_ROOT"/.claude/checks/*.sh; do
    [ -f "$f" ] || continue
    name=$(basename "$f" .sh)
    rg_is_disabled "$name" && continue
    out=$(bash "$f" 2>&1)
    rc=$?
    if [ "$rc" -eq 0 ]; then
      CHECKS_REPORT="$CHECKS_REPORT[ok]   $name"$'\n'
    else
      FLAGGED="$FLAGGED $name"
      CHECKS_REPORT="$CHECKS_REPORT[FLAG] $name"$'\n'
    fi
    [ -n "$out" ] && CHECKS_REPORT="$CHECKS_REPORT$(printf '%s\n' "$out" | sed 's/^/         /')"$'\n'
  done
  return 0
}

report() {
  echo "Base: origin/$RG_BASE   merge-base: ${RG_MB:0:9}   HEAD: $(git rev-parse --short HEAD)   fingerprint: $FP"
  printf '%s' "$CHECKS_REPORT"
  echo "Judgement checks, run these skills in order: ${RG_SKILLS[*]}"
  if [ "${#RG_VERIFY[@]}" -gt 0 ]; then
    echo "Verify commands:"
    printf '  %s\n' "${RG_VERIFY[@]}"
  else
    echo "Verify commands: none configured, ask the developer what to run"
  fi
  if [ -f "$STATE/$FP" ]; then echo "Gate: APPROVED for this exact diff"; else echo "Gate: NOT approved for this diff"; fi
}

is_protected() {
  case "$1" in main | master | production | release-*) return 0 ;; esac
  return 1
}

cmd_status() {
  collect || exit 2
  report
  [ -z "$FLAGGED" ]
}

cmd_approve() {
  local checks="" confirmed=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --checks) checks=$2; shift 2 ;;
      --confirmed) confirmed=$2; shift 2 ;;
      *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
  done
  collect || exit 2
  report
  if [ -z "$checks" ]; then echo "Refused: --checks must say which verify commands you ran and their result." >&2; exit 2; fi
  if [ -n "$FLAGGED" ] && [ -z "$confirmed" ]; then
    echo "Refused: flagged checks:$FLAGGED. Ask the developer, then pass --confirmed \"<what they confirmed>\"." >&2
    exit 2
  fi
  mkdir -p "$STATE"
  {
    echo "approved: $(date -u +%FT%TZ)"
    echo "head: $(git rev-parse HEAD)"
    echo "flagged:$FLAGGED"
    echo "checks: $checks"
    echo "confirmed: $confirmed"
  } >"$STATE/$FP"
  echo "Approved fingerprint $FP. Push is now allowed for this exact diff."
}

cmd_hook() {
  local input command branch
  input=$(cat)
  if command -v jq >/dev/null 2>&1; then
    command=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
  else
    command=$(printf '%s' "$input" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{console.log(JSON.parse(s).tool_input.command||"")}catch(e){}})')
  fi
  local sep='(^|[;&|(`[:space:]])'
  local push="${sep}git([[:space:]]+(-C|-c)[[:space:]]+[^[:space:]]+|[[:space:]]+--[a-z-]+(=[^[:space:]]+)?)*[[:space:]]+push([[:space:]]|\$)"
  local pr="${sep}gh[[:space:]]+pr[[:space:]]+(create|ready)([[:space:]]|\$)"
  if ! [[ "$command" =~ $push ]] && ! [[ "$command" =~ $pr ]]; then exit 0; fi
  [[ "$command" == *--dry-run* ]] && exit 0

  branch=$(git symbolic-ref --short -q HEAD)
  local dest='(^|[[:space:]:])(refs/heads/)?(main|master|production|release-[^[:space:]]*)([[:space:]]|$)'
  if [[ "$command" =~ $push ]] && { is_protected "$branch" || [[ "$command" =~ $dest ]]; }; then
    echo "BLOCKED: push to main/master/production/release-* is not allowed. Changes reach them only through a pull request that a human merges (AGENTS.md)." >&2
    exit 2
  fi

  if ! collect; then echo "BLOCKED: the gate could not compute the diff (see above)." >&2; exit 2; fi
  if [ -z "$(git diff --no-renames "$RG_MB" HEAD)" ] || [ -f "$STATE/$FP" ]; then exit 0; fi
  {
    echo "BLOCKED by railguards: this diff has not been through the gate."
    report
    echo
    echo "Run the railguards:gate skill. It runs the judgement skills above, then the verify commands."
    echo "Show the developer every flagged item, get their explicit confirmation, then approve with:"
    echo "  bash \"$SELF\" approve --checks \"...\" --confirmed \"...\""
    echo "Do not create files in .claude/.railguards by hand and do not edit the gate to get past it."
  } >&2
  exit 2
}

case "${1:-status}" in
  status) cmd_status ;;
  approve) shift; cmd_approve "$@" ;;
  hook) cmd_hook ;;
  *) echo "usage: gate.sh status | approve --checks ... [--confirmed ...] | hook" >&2; exit 2 ;;
esac
