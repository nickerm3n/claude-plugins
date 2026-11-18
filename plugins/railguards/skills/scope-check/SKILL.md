---
name: scope-check
description: Compare a diff with the task and find every change nobody asked for or that needs clarification. Use before a push, as a step of the gate pipeline, or when a change looks bigger than the task.
---

# Scope check

The question is not "is the code good" but "did anyone ask for this".

## Get the task

In this order: the user's request in this conversation; the Jira ticket named in the branch (`PROJ-1234`, via the Jira tools if available); otherwise ask the developer for the task in one sentence. Do not review scope against a guess.

## Method

1. Write the task as a short list of acceptance points (what must be true after the PR).
2. Read `git diff origin/<base>...HEAD` hunk by hunk. Map each hunk to an acceptance point.
3. Every hunk with no point is an **unrequested change**. Typical ones:
   - renames, reformatting, import reordering, moved code
   - "while I was here" fixes, refactors of neighbouring code
   - new abstractions, helpers, options, types, props or config nobody needs yet
   - changed behaviour of shared code that the task did not mention (callers outside the diff still inherit it)
   - dependency, lockfile, native, CI or config changes
   - tests for behaviour the task did not touch; removed or loosened existing tests
   - new fallbacks, retries, try/catch, logging, analytics
4. Also list **gaps in the task**: behaviour the diff had to decide that the task is silent about (empty state, error state, tablet vs phone, logged-out user, permission, a field's default). These are questions for the developer, not for you to settle quietly.

## Output

A table: `hunk or file | maps to | verdict`, where verdict is `in scope`, `unrequested: remove` or `needs answer: <question>`.

Then act: remove unrequested hunks from the diff yourself (they are your additions, undo them), and ask the developer the open questions. A hunk stays only if the developer says in this conversation that they want it, and that confirmation is recorded with `--confirmed` at approval.
