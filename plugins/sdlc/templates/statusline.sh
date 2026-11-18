#!/usr/bin/env bash
# Claude Code status line for sdlc. /sdlc:init copies it to .sdlc/statusline.sh and points .claude/settings.json at it.
# Shows the run of the current branch (Jira key in the branch name) or the most recently updated live run.
#   sdlc PROJ-123 ▸ design 4/10 ⏸ waiting for human
input=$(cat)
dir=$(printf '%s' "$input" | jq -r '.workspace.project_dir // .cwd // empty' 2>/dev/null)
dir=${dir:-$PWD}
runs="$dir/.sdlc/runs"
[ -d "$runs" ] || exit 0
branch=$(git -C "$dir" symbolic-ref --short -q HEAD 2>/dev/null)
key=$(printf '%s' "$branch" | grep -oE '[A-Z][A-Z0-9]+-[0-9]+' | head -1)
file=""
[ -n "$key" ] && [ -f "$runs/$key/run.json" ] && file="$runs/$key/run.json"
if [ -z "$file" ]; then
  file=$(ls -t "$runs"/*/run.json 2>/dev/null | while read -r f; do
    [ "$(jq -r .status "$f")" != "done" ] && { echo "$f"; break; }
  done)
fi
[ -n "$file" ] || exit 0
jq -r '
  .current as $c
  | (.phases | index($c)) as $i
  | {"running":"","waiting_human":" ⏸ waiting for human","escalated":" ⛔ escalated","done":" ✓ done"}[.status] as $s
  | (if $c == "code" and .plan_step then " step \(.plan_step)" else "" end) as $step
  | ((.retries[$c] // 0) as $r | if $r > 0 then " ↻\($r)" else "" end) as $retry
  | "sdlc \(.key) ▸ \(.current) \($i + 1)/\(.phases | length)\($step)\($retry)\($s)"
' "$file"
