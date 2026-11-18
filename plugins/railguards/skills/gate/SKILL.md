---
name: gate
description: Pre-push pipeline that keeps pull requests small, in scope and safe. Run it before any git push, gh pr create, or when the user says push, open a PR, ship it or done. A hook blocks the push until this gate approves the exact diff.
---

# Railguards gate

A hook (`hooks/gate.sh` in this plugin) blocks `git push` and `gh pr create` until the current diff has an approval. This skill is how you earn it. A push is only ever done after the user asked for it (AGENTS.md); the gate is the second condition, not a substitute for the first.

The pipeline is data, not text: the script and the project's `.claude/railguards.conf` decide which checks and skills run. Do not run a fixed list from memory.

## Pipeline

Stop and ask the developer at the first step that raises a question; do not batch guesses.

1. **Sync and status.** `git fetch origin <base>` (base is in the conf), then `bash "${CLAUDE_PLUGIN_ROOT}/hooks/gate.sh" status`. It runs every deterministic check (`checks/*.sh`, plus the project's `.claude/checks/*.sh`) and prints the report, the judgement skills to run, and the verify commands. Read `git diff origin/<base>...HEAD` yourself, all of it.
2. **Judgement checks.** Invoke each skill the status lists under "run these skills in order". By default: `railguards:scope-check` (does every hunk trace to the task), `railguards:guards-check` (is a guarded area touched), `railguards:clean-diff` (smallest, simplest, no side effects, no comments).
3. **Verify.** Run every verify command the status lists, on the final diff, and read the output. Do not claim a check passed without having run it in this step. If none are configured, ask the developer what to run. Pre-existing failures: show that they fail on the base too, do not fix them in this PR.
4. **Report.** One message to the developer: what changed in a sentence, every `[FLAG]` and every finding from the skills with its file, and the verification results. Ask for explicit confirmation of each flag. Silence or a general "ok" does not confirm a flag you have not named.
5. **Approve.** Only after the developer confirmed (or when there were no flags):
   `bash "${CLAUDE_PLUGIN_ROOT}/hooks/gate.sh" approve --checks "<commands and results>" [--confirmed "<what the developer confirmed, in their words>"]`
   `--confirmed` is mandatory when any check is flagged.
6. **Push.** Only if the user asked for the push in this conversation. Use an explicit refspec: `git push origin HEAD:refs/heads/<branch>`.

## Rules

- Any new commit or amend changes the fingerprint and voids the approval. Re-run from step 1.
- If the size check flags the diff, the default answer is to split the PR, not to ask for an exception. Offer the split first.
- Never create files in `.claude/.railguards/` yourself, never edit the hook, the checks, the conf or these skills to get past the gate, and never look for another route around it (a different command, a script, another remote).
- Do not post PR comments or review comments unless the user asks.
