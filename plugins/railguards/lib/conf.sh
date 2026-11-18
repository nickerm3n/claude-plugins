# Shared by hooks/gate.sh and every check. Source it; it never exits.
# Reads the project's .claude/railguards.conf (tab-separated):
#   set     base | max_files | max_lines     <value>
#   guard   <glob>   <reason>               diff touching it is flagged
#   ignore  <glob>                          not counted, not scanned (generated or lock files)
#   verify  <command>                       run on the final diff before approval
#   skill   <plugin:skill>                  judgement check, run in order (default: RG_DEFAULT_SKILLS)
#   disable <check name>                    turn a check off
# Globs are shell `case` patterns: `*` also matches `/`.

RG_ROOT="${RG_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null)}"
RG_CONF="$RG_ROOT/.claude/railguards.conf"
RG_BASE=main RG_MAX_FILES=8 RG_MAX_LINES=200
RG_GUARD_GLOBS=() RG_GUARD_WHY=() RG_IGNORE_GLOBS=() RG_VERIFY=() RG_SKILLS=() RG_DISABLED=()
RG_DEFAULT_SKILLS=(railguards:scope-check railguards:guards-check railguards:clean-diff)

if [ -f "$RG_CONF" ]; then
  while IFS=$'\t' read -r kind a b; do
    case "$kind" in
      set) case "$a" in base) RG_BASE=$b ;; max_files) RG_MAX_FILES=$b ;; max_lines) RG_MAX_LINES=$b ;; esac ;;
      guard) RG_GUARD_GLOBS+=("$a"); RG_GUARD_WHY+=("$b") ;;
      ignore) RG_IGNORE_GLOBS+=("$a") ;;
      verify) RG_VERIFY+=("$a") ;;
      skill) RG_SKILLS+=("$a") ;;
      disable) RG_DISABLED+=("$a") ;;
    esac
  done < <(grep -v '^[[:space:]]*#' "$RG_CONF")
fi
[ "${#RG_SKILLS[@]}" -eq 0 ] && RG_SKILLS=("${RG_DEFAULT_SKILLS[@]}")

rg_is_ignored() {
  local g
  for g in "${RG_IGNORE_GLOBS[@]}"; do
    case "$1" in $g) return 0 ;; esac
  done
  return 1
}

rg_is_disabled() {
  local d
  for d in "${RG_DISABLED[@]}"; do
    [ "$d" = "$1" ] && return 0
  done
  return 1
}
