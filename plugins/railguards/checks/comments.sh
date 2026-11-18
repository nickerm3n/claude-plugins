#!/usr/bin/env bash
# Flags newly added code comments in .ts/.tsx/.js/.jsx files. Directives that do work (eslint, @ts-*, prettier) are not comments.
. "$(dirname "$0")/../lib/conf.sh"
found=0
while IFS= read -r path; do
  case "$path" in *.ts | *.tsx | *.js | *.jsx) ;; *) continue ;; esac
  rg_is_ignored "$path" && continue
  n=$(git diff -U0 --no-renames "$RG_MB" HEAD -- "$path" | grep -E '^\+' | grep -vE '^\+\+\+' \
    | grep -E '^\+[[:space:]]*(//|/\*|\*([[:space:]]|/|$)|\{/\*)' \
    | grep -vE 'eslint-|@ts-(ignore|expect-error|nocheck|check)|prettier-ignore|istanbul|<reference|@jsx|@flow|@refresh' | wc -l | tr -d ' ')
  if [ "$n" -gt 0 ]; then echo "$path: $n new comment line(s)"; found=1; fi
done < <(git diff --name-only --no-renames "$RG_MB" HEAD)
[ "$found" -eq 0 ] && echo "none"
exit "$found"
