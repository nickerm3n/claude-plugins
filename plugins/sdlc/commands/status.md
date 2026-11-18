---
description: Show where the AI SDLC runs are - current phase, retries, approvals, last gate events - and the board
argument-hint: "[<JIRA-KEY>] [--open]"
allowed-tools: Bash(python3:*), Bash(open:*), Bash(xdg-open:*)
---

# /sdlc:status

Arguments: `$ARGUMENTS`.

1. If `.sdlc/config.yml` is missing, say the repo is not set up (`/sdlc:init`) and stop.
2. With a key: `python3 "${CLAUDE_PLUGIN_ROOT}/gates/state.py" show <KEY>`. Without: `python3 "${CLAUDE_PLUGIN_ROOT}/gates/state.py" list`, then `show` for the run of the current branch if there is one.
3. `python3 "${CLAUDE_PLUGIN_ROOT}/gates/board.py"` re-renders the board; with `--open` add `--open` to open it in the browser.
4. Reply with the output as is (it is already short), then one line on what unblocks the run:
   - `waiting for human` at design: the `design-approved` label on the PR (or `/sdlc:approve design`)
   - `escalated`: the engineer decides, `/sdlc:approve <phase>` to continue or `/sdlc:rewind <phase>` to go back
   - `running`: `/sdlc:feature <KEY>` resumes it
   and the board path (`.sdlc/runs/index.html`).

Change nothing: this command only reads.
