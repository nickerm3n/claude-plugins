---
description: Run (or resume) the 10-phase AI SDLC feature pipeline for a Jira issue
argument-hint: "<JIRA-KEY> [--dry-run]"
---

# /sdlc:feature

Run the `feature` pipeline for `$ARGUMENTS`.

Invoke the `sdlc:orchestrator` skill and follow it exactly, with:
- pipeline: `feature`
- Jira key and flags: `$ARGUMENTS` (`--dry-run`: artifacts only, no code, no PR)

If the key is missing, ask for it. If a run for the key exists, the orchestrator resumes it from its current phase; it never starts over on its own.
