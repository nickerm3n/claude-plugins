---
description: Set up the AI SDLC pipeline in this repository - detect the stack, confirm commands, write .sdlc/config.yml, domain-map.yml and the architecture principles skeleton
argument-hint: "[--force]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# /sdlc:init

Set up `.sdlc/` for this repository. Everything stack-specific lives in the project, never in the plugin. Arguments: `$ARGUMENTS`.

Plugin scripts: `G="${CLAUDE_PLUGIN_ROOT}/gates"`, templates in `${CLAUDE_PLUGIN_ROOT}/templates`.

## Steps

1. **Existing setup.** If `.sdlc/config.yml` exists and `--force` was not passed, show `python3 "$G/state.py" list` and stop: the project is already set up.
2. **Detect.** Run `python3 "$G/detect_stack.py" --root .` and read the README, `package.json` scripts / `Makefile` / CI workflows to see which commands the team really runs. The presets are guesses.
3. **Confirm commands with the engineer.** One AskUserQuestion round, then follow-ups for anything unclear:
   - `test`: must run the full suite (the Code gate refuses partial runs), `lint`, `coverage`, `complexity`, `mutation`, `sast`, `dast`, `deploy` (test environment), `e2e` (runs the QA plan scenarios).
   - Anything the project does not have: write `none` on purpose, do not invent a tool the repo does not use.
   - Baseline: run `test` and `lint` once on a clean base branch. Both must be green, or the Code gate can never pass: stop and tell the engineer. Count the skipped/pending tests the output reports and set `gates.skipped_tests_regex` and `gates.skipped_tests_baseline` to that count.
   - Quality tools: `complexity` needs `lizard` (`pip install lizard`) writing `reports.complexity`, `coverage` writes lcov or Cobertura, `sast` is the project's scanner. Install what the config calls, then run `python3 "$G/run_gate.py" ci` once on a clean base branch: it proves the commands work. Complexity and CRAP are judged on changed functions only (`gates.ci_scope`), so legacy code does not block a feature. Leave out only what the engineer names, in `gates.ci_skip`.
   - Thresholds (`crap_max`, `complexity_max`, `mutation_score_min`): the video gives no numbers, so leave `null` unless the team names values.
4. **Jira.** Ask for the Jira base URL and project key. Credentials are never written to the repo: tell the engineer to export `JIRA_EMAIL` and `JIRA_API_TOKEN` (shell profile or a secret manager), then run `python3 "$G/jira.py" check`. If they use the Atlassian MCP server instead, note that the orchestrator will use it.
5. **Deploy.** Ask how a change reaches the test environment. A branch deploy: `commands.deploy` does it. CI deploys the base branch after a merge: set `human.merge_before_deploy: true` and write a project script that waits for that deploy of `$SDLC_MERGE_SHA`. If the e2e suite already fails on the test environment, record those tests as known failures in a project script; never let the QA gate depend on a red baseline.
6. **Design approval.** Ask: team review on a draft PR with the `design-approved` label (default, `github-label:design-approved`) or approval in the session with `/sdlc:approve design` (`state`).
7. **Domains.** Ask which parts of the code are core, supporting and generic (DDD), and who owns core. Write `.sdlc/domain-map.yml` from `templates/domain-map.yml`.
8. **Write files.**
   - `.sdlc/config.yml` from `templates/config.yml` with the confirmed values. Validate: `python3 "$G/state.py" list` must not print a config error.
   - `docs/architecture/principles/` from `templates/architecture-principles/` if it does not exist. Tell the engineer the architecture judge is only as good as these files: they describe, update and improve them.
   - `.github/pull_request_template.md` from `templates/pull_request_template.md` if the repo has none (ask before overwriting one).
   - `.sdlc/statusline.sh` from `templates/statusline.sh` (`chmod +x`), and offer to point `.claude/settings.json` `statusLine` at it: `{"type": "command", "command": ".sdlc/statusline.sh"}`. If a status line is already set, show both and let the engineer choose.
   - Add `.sdlc/reports/` and `.sdlc/runs/index.html` (the board, regenerated locally) to `.gitignore`. Run artifacts in `.sdlc/runs/` are committed to the feature branch on purpose (the team reviews design in the PR).
9. **CI.** Show the snippet from the plugin README ("Hard CI") that calls the reusable `sdlc-ci-quality.yml` workflow. Do not add it without the engineer's yes.
10. **Review policy.** Print `python3 "$G/domain.py" codeowners` and `python3 "$G/domain.py" checklist`. CODEOWNERS and branch protection are installed by a human; offer to write `CODEOWNERS`, never change GitHub settings.
11. **Report.** List the files written, the commands set to `none`, the open thresholds, and the next step: `/sdlc:feature <JIRA-KEY>` (or `--dry-run` first).

Do not commit anything; the engineer reviews the files first.
