---
name: enrich
description: Enrich phase of the AI SDLC pipeline - interview the engineer (grill-me style) until their view of the task, the decisions, constraints and pitfalls are on paper, then write 02-enrich.md. Run by the sdlc orchestrator in the main session; the engineer is in the loop.
---

# Enrich: get the task out of the engineer's head

What reaches production is not how the customer sees the feature but how the developer understood it. The engineer has a swarm of thoughts about how the system works and where the traps are; this phase puts them into the context before any agent researches or designs. The idea comes from the `grill-me` skill the video names; this version is ours.

## Inputs

`.sdlc/runs/<KEY>/01-task.md`. Read it fully. You may skim the code to ask sharper questions, but do not research: that is the next phase.

## Interview

- One question at a time, most important first. Each question names what you already understood and asks for what is missing. Offer 2–4 concrete options when it helps (AskUserQuestion), the engineer can always answer in their own words.
- Cover, in roughly this order, skipping what the task already answers:
  1. **Intent.** What problem this solves, for whom, what "done" looks like beyond the acceptance criteria.
  2. **Where it lives.** Which parts of the system it touches, which it must not.
  3. **Decisions already made.** Approaches the engineer wants or rules out, and why.
  4. **Constraints.** Contracts that must not change, performance, security, data, rollout, backwards compatibility, deadlines.
  5. **Pitfalls.** What broke last time someone touched this, hidden coupling, flaky areas, things only the team knows.
  6. **Edge cases.** Empty, error, permission, concurrency, migration. Ask about the ones that matter for this task, not a checklist.
  7. **Out of scope.** What the engineer explicitly does not want in this change.
- Push back when an answer is vague ("make it robust"): ask for the concrete case.
- Stop when another question would not change the design. Usually 5–12 questions. Ask the engineer "Anything I did not ask that the designer must know?" last.

## Output: `.sdlc/runs/<KEY>/02-enrich.md`

In `project.artifact_language`, headings exactly as below (the gate checks them):

```markdown
# <KEY> · Enrich

## Engineer's view
The task in the engineer's words: intent, where it lives, what done means.

## Decisions
- <decision> — <why, in the engineer's words>

## Constraints
- <constraint>

## Pitfalls
- <pitfall and where it is>

## Open questions
- <question nobody could answer yet, and who can>

## Out of scope
- <thing>
```

Keep it short: facts and decisions, not a transcript. Do not add anything the engineer did not say; mark your own inference as "(inferred, confirm)". Then hand back to the orchestrator, which asks the engineer to confirm.
