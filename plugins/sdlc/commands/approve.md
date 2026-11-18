---
description: Human approval of an AI SDLC phase (design review, or continue after an escalation)
argument-hint: "<phase> [<JIRA-KEY>] [note]"
disable-model-invocation: true
allowed-tools: Bash(python3:*), Bash(git config:*)
---

# /sdlc:approve

The engineer typed this command; it is the human approval the pipeline waits for. Arguments: `$ARGUMENTS`.

1. Parse `<phase>` (required), an optional Jira key, and the rest as a note.
2. Name: `git config user.name`.
3. `python3 "${CLAUDE_PLUGIN_ROOT}/gates/state.py" approve <phase> --by "<name>" [--key <KEY>]`
4. Show the new status line and say what happens next:
   - `design`: QA Plan starts on `/sdlc:feature <KEY>`. If the project uses the label rule, the label is still required.
   - `code` after a judge escalation: the engineer chose **fix the code only**; the coder gets the judge findings on resume.
   - any escalated phase: retries are reset and the phase runs again on resume.

Never run this on your own initiative: only when the engineer typed `/sdlc:approve`.
