#!/usr/bin/env bash
# Flags every changed path that matches a `guard` glob in railguards.conf.
. "$(dirname "$0")/../lib/conf.sh"
hits=0
while IFS= read -r path; do
  i=0
  while [ "$i" -lt "${#RG_GUARD_GLOBS[@]}" ]; do
    g=${RG_GUARD_GLOBS[$i]}
    case "$path" in $g) echo "$path  <-  ${RG_GUARD_WHY[$i]}"; hits=1 ;; esac
    i=$((i + 1))
  done
done < <(git diff --name-only --no-renames "$RG_MB" HEAD)
[ "$hits" -eq 0 ] && echo "none"
exit "$hits"
