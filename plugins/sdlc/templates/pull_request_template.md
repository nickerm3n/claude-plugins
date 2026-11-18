## What and why

<!-- One paragraph. Link the Jira issue. -->

Jira: <KEY>

## AI SDLC run

- Artifacts: `.sdlc/runs/<KEY>/` (design: `04-design.md`, QA plan: `05-qa-plan.md`, plan: `06-plan.md`)
- Gates passed: <!-- from `/sdlc:status <KEY>` -->

## Domain class and review depth

<!-- from `domain.py classify`: core | supporting | generic -->

| Class | Review |
|---|---|
| core | 1+ engineers, full depth, run it locally |
| supporting | the author may review, reduced depth |
| generic | skim: design was reviewed, tests pass |

## Checklist

- [ ] Design reviewed by the team (`design-approved`)
- [ ] Hard CI green (complexity, CRAP, mutation, coverage, lint, SAST)
- [ ] QA plan scenarios pass (`10-qa.md`)
