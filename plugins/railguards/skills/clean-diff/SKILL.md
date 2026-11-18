---
name: clean-diff
description: Check that a change is the smallest, simplest version that does the task, with no side effects and no new comments. Use as a step of the gate pipeline, while writing code, and whenever a diff feels bigger than the task.
---

# Clean diff

The best PR is the one a reviewer reads in two minutes. Apply these rules while writing code, then check them again on the final diff.

## Rules

1. **Minimal.** Fewest files, fewest lines that fully do the task. Prefer editing the existing code path over adding a new one. Prefer deleting code to adding code.
2. **Simple.** The obvious solution a new teammate would expect. No new abstraction, helper, hook, context, type, option, prop or config for a single use. No generalising for a second case that does not exist. Reuse what the codebase already has before writing anything.
3. **No side effects.** The diff changes only what the task names. Shared code that other screens import is changed only if the task says so; if it must change, name every consumer. No behaviour changes hidden in a refactor.
4. **No drive-bys.** No reformatting, import reordering, renaming, moving code, fixing neighbouring lint warnings, upgrading dependencies, or touching lockfiles, native, CI or config unless the task asks. Run Prettier only on lines you changed (do not let it rewrite a whole file).
5. **No new comments.** Do not add `//`, `/* */`, JSDoc or JSX comments to code, tests or config. Names and structure carry the meaning. Directives that do work (`eslint-disable-next-line`, `@ts-expect-error`) are not comments but need a reason from the developer. Do not leave commented-out code or TODOs. Do not post PR or review comments unless the user asks.
6. **No speculative safety.** No extra null checks, try/catch, fallbacks, retries, logging or validation beyond what the task and the types require.
7. **Tests match the change.** A test for the behaviour you changed, next to the existing tests; nothing else.

## Check on the final diff

Read `git diff origin/<base>...HEAD` and for each file answer: can this hunk be deleted without failing the task? Can this be said with fewer lines? Is there a simpler way? Then:

- Remove what you can remove, simplify what you can simplify. The built-in `/simplify` skill may be used to shrink the diff, never to add to it: review whatever it changed.
- Anything left that goes beyond these rules (an extra abstraction, a shared-code change, a comment) is allowed only if the developer says in this conversation that they really want it. Ask once, state the cost in a sentence, and record the answer with `--confirmed`. If they are not sure, remove it.
- If the diff is over the size limit in `.claude/railguards.conf`, propose how to split it into separate PRs before asking for an exception.
