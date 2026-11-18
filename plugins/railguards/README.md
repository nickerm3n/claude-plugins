# railguards

Keeps pull requests small, in scope and safe.

- `hooks/gate.sh hook` is a PreToolUse hook. It blocks `git push` and `gh pr create` until the exact diff has been approved, and always blocks pushes to `main`, `master`, `production` and `release-*`.
- Approval is stored per diff fingerprint in `.claude/.railguards/` of the project (add it to `.gitignore`). A new commit voids it.
- `skills/gate` is the pipeline the agent follows to earn the approval.

## Two kinds of check

| Kind | Where | Good for | How it fails the gate |
| --- | --- | --- | --- |
| Deterministic check | `checks/<name>.sh` in the plugin, or `.claude/checks/<name>.sh` in a project | things a script can decide: size, paths, patterns | exits 1; the developer must confirm it |
| Judgement check | a skill, listed by `skill` lines in the project conf | things that need reading: scope, side effects, risk | the agent reports it; the developer confirms |

Built in: `size`, `guards`, `comments` (scripts) and `scope-check`, `guards-check`, `clean-diff` (skills).

### Add a deterministic check

Drop an executable script in `checks/` (every project) or `.claude/checks/` (one project). The runner calls `bash <script>` with `RG_ROOT`, `RG_BASE`, `RG_MB` (merge-base) set. Source `lib/conf.sh` to read the project conf. Print what the developer should see; exit 0 when clean, 1 when flagged. The diff is `git diff "$RG_MB" HEAD`. Example:

```bash
#!/usr/bin/env bash
. "$(dirname "$0")/../lib/conf.sh"
if git diff --name-only "$RG_MB" HEAD | grep -q 'package.json$'; then
  echo "package.json changed: say why a dependency is needed"
  exit 1
fi
```

### Add a judgement check

Write a skill (in this plugin or another one) and list it in the project conf, in the order it should run: `skill<TAB>other-plugin:perf-check`. Listing any `skill` line replaces the default list, so list the built-ins too.

## Project conf: `.claude/railguards.conf`

Tab-separated, `#` comments. See `lib/conf.sh` for every directive: `set` (`base`, `max_files`, `max_lines`), `guard`, `ignore`, `verify`, `skill`, `disable`.
