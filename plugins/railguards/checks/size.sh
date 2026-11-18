#!/usr/bin/env bash
# Check protocol: env RG_ROOT RG_BASE RG_MB; print what the developer should see; exit 0 clean, 1 flagged.
. "$(dirname "$0")/../lib/conf.sh"
files=0 total=0
while IFS=$'\t' read -r add del path; do
  rg_is_ignored "$path" && continue
  files=$((files + 1))
  [ "$add" = "-" ] && add=0
  [ "$del" = "-" ] && del=0
  total=$((total + add + del))
done < <(git diff --numstat --no-renames "$RG_MB" HEAD)
echo "$files files, $total changed lines (limits $RG_MAX_FILES files / $RG_MAX_LINES lines; ignored files not counted)"
if [ "$files" -gt "$RG_MAX_FILES" ] || [ "$total" -gt "$RG_MAX_LINES" ]; then
  echo "over the limit: split the PR, or get the developer to confirm it"
  exit 1
fi
