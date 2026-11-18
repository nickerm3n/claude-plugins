---
description: Human decision to roll an AI SDLC run back to an earlier phase (e.g. Code -> Design after the architecture judge found a design error)
argument-hint: "<phase> <reason> [--key <JIRA-KEY>]"
disable-model-invocation: true
allowed-tools: Bash(python3:*), Bash(git config:*)
---

# /sdlc:rewind

The engineer typed this command. Arguments: `$ARGUMENTS`.

1. Parse `<phase>`, the reason (the rest of the text) and an optional `--key`.
2. `python3 "${CLAUDE_PLUGIN_ROOT}/gates/state.py" rewind <phase> --by "$(git config user.name)" --reason "<reason>" [--key <KEY>]`
3. Phases from `<phase>` on are reset: their approvals and retries are cleared, artifacts stay on disk for the agents to revise. Code already committed stays in the branch; say so, and that the coder will rework it after the new design.
4. Show `state.py show` and tell the engineer `/sdlc:feature <KEY>` resumes from `<phase>`.

Never run this on your own initiative.
