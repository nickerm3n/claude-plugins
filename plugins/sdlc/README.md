# sdlc

AI SDLC pipeline for Claude Code: a Jira issue goes through ten phases, each in its own context with its own artifact, and a gate between every pair of phases. The gate checks with code first, then a judge agent, then a human. The human is in the loop on Enrich and Design and decides every escalation; on the other phases they watch.

The plugin knows no stack. Every command (tests, linters, coverage, mutation, SAST, deploy, e2e) comes from the project's `.sdlc/config.yml`.

```
Task → Enrich → Research → Design → QA Plan → Plan → Code → QA Check → Deploy → QA
 Jira   human              human                    per plan
                                                     phase
```

| # | Phase | Who | Artifact (`.sdlc/runs/<KEY>/`) | Gate (code) | Judge | Human |
|---|---|---|---|---|---|---|
| 1 | Task | `jira.py` / Atlassian MCP | `01-task.md` | `Key:` line, summary, acceptance criteria | — | supplies AC if Jira has none |
| 2 | Enrich | skill `enrich` (interview) | `02-enrich.md` | sections, decisions and constraints not empty | — | **in the loop** |
| 3 | Research | agent `researcher` | `03-research.md` | sections, every referenced `path:line` exists | `judges.research` | watches |
| 4 | Design | agent `designer` | `04-design.md` | sections, C4 + sequence + data-flow mermaid that parse | `judges.design` | **team review on a draft PR, always** |
| 5 | QA Plan | agent `qa-planner` | `05-qa-plan.md` | contracts, scenarios with `QA-n` ids, tests | — | watches |
| 6 | Plan | agent `planner` | `06-plan.md` | `### Phase N:` with `Goal:` and `Done when:`, no code, size limit | `judges.plan` | watches |
| 7 | Code | agent `coder`, per plan phase | code, commits, `07-code.md` | PR open, real diff, lint, **full** test suite, no skipped tests, no forbidden patterns | `judge-architecture` (always) | decides on a design issue |
| 8 | QA Check | agent `qa-checker` | `08-qa-check.md`, updated `05` | every `QA-n` has a status | — | decides on "return to code" |
| 9 | Deploy | `commands.deploy` | `09-deploy.md` | command exit 0; with `human.merge_before_deploy` first the PR must be merged | — | merges the PR when CI deploys the base branch |
| 10 | QA | `commands.e2e` | `10-qa.md` | command exit 0 | — | watches |

Section names, rubrics, ids and limits are our decisions; the video the pipeline comes from does not show them.

## Use in a project

One engineer, in a session:

```
/plugin install sdlc --marketplace nickerm3n/claude-plugins
```

The whole team, in the project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "claude-plugins": { "source": { "source": "github", "repo": "nickerm3n/claude-plugins" } }
  },
  "enabledPlugins": { "sdlc@claude-plugins": true }
}
```

Then, in the project:

```
/sdlc:init                 detect the stack, confirm commands, write .sdlc/config.yml, domain map, principles skeleton
/sdlc:feature PROJ-123      run (or resume) the pipeline for a Jira issue; --dry-run: artifacts only, no code
/sdlc:status [PROJ-123]     where the runs are; --open opens the board
/sdlc:approve design       human approval (design in `state` mode, or continue after an escalation)
/sdlc:rewind design <why>  human decision to go back, e.g. after the architecture judge found a design error
/sdlc:bugfix PROJ-124       the project's own `pipelines.bugfix` phase set
```

`/sdlc:approve` and `/sdlc:rewind` have `disable-model-invocation`: only the engineer can run them.

Requirements: `python3` ≥ 3.9 (stdlib only; PyYAML is used when installed), `git`, `gh` (authenticated), `jq` for the status line. Optional: `mmdc` (mermaid-cli) for a full diagram parse instead of the structural one.

Jira: export `JIRA_EMAIL` and `JIRA_API_TOKEN` (and `JIRA_BASE_URL`, or set `tracker.base_url`). Never put them in the repo. Without them the orchestrator uses connected Atlassian MCP tools, or asks you to paste the issue.

## Where to see the stage

- **Status line**: `/sdlc:init` installs `.sdlc/statusline.sh`: `sdlc PROJ-123 ▸ design 4/10 ⏸ waiting for human`.
- **Board**: `.sdlc/runs/index.html`, regenerated on every state change, reloads itself while a run is live. Phases, retries, approvals, links to artifacts, the gate history.
- **`/sdlc:status`** in the session.
- **Pane beside the chat** (`hooks/pane.tsx`): the run as a gate state machine. Every phase with its gate steps (code check → judge → you), the current step expanded, and a callout with the one action the run waits for (Approve design, I merged it, Retry phase, Fix code only). A minimal state-machine graph shows the ten phases as nodes (`●━━●━━◉┈┈○`), the edge a run just crossed lights up for a few seconds, and arcs underneath draw the paths that go backwards (`▴────╯ rewind`, `▴────╯ design issue`); a retry shows as `↺n` on the pointer. The **List** / **Graph** button switches to the per-phase list. Opens by itself when a run is live; `/sdlc-pane` opens it any time. The same summary sits under the prompt as a status entry. The pane uses the hooks-module API, which is early access in Claude Code.

## How a gate works

```
phase agent finishes → SubagentStop hook → run_gate.py <phase>
  fail → the agent is sent back with the violations, retry++
  retry > gates.max_retries → run escalated, the engineer decides
pass → judge (if configured, other model) → PASS / FAIL (retry) / DESIGN_ISSUE (stop, ask)
     → human (Enrich, Design, escalations) → next phase
```

The orchestrator runs the same gate again after each agent, so the run is safe even with hooks off. State lives in `.sdlc/runs/<KEY>/run.json` and moves only through `gates/state.py`.

Scripts (all `python3 "${CLAUDE_PLUGIN_ROOT}/gates/<script>"`, run from the repo root):

| Script | What |
|---|---|
| `run_gate.py <phase>` | the deterministic gate of a phase; `approval`, `judge`, `ci`, `crap`, `plan-phases`, `hook` |
| `state.py` | `init`, `show`, `list`, `start`, `pass`, `fail`, `wait`, `approve`, `rewind`, `step`, `set-pr` |
| `board.py [--open]` | render the board |
| `jira.py` | `fetch <KEY> [--write]`, `comment <KEY> --file`, `check` |
| `domain.py` | `classify` (domain class of the diff), `codeowners`, `checklist` (branch protection) |
| `detect_stack.py` | presets for `/sdlc:init` |

`deploy` and `e2e` run with `SDLC_KEY`, `SDLC_BRANCH`, `SDLC_BASE`, `SDLC_PR_URL`, `SDLC_MERGE_SHA` and `SDLC_RUN_DIR` in the environment, so a project script can wait for the CI deploy of the merge commit or start its e2e workflow.

Exit codes: 0 pass, 1 fail, 2 usage or config error, 3 escalate (judge design issue, or retries exhausted).

## Hard CI

Before a PR is merged: cyclomatic and cognitive complexity, CRAP (`comp² × (1 − cov)³ + comp`, computed by the plugin from a `lizard --csv` report and lcov or Cobertura coverage), mutation score (mutation-testing-report JSON: Stryker, PIT report plugin), coverage, linters, SAST, DAST. 0 tokens, runs in the background.

The project calls the reusable workflow of this repository:

```yaml
# .github/workflows/quality.yml in the project
name: quality
on:
  pull_request:
  schedule: [{ cron: "0 3 * * *" }]
jobs:
  sdlc:
    uses: nickerm3n/claude-plugins/.github/workflows/sdlc-ci-quality.yml@main
    with:
      setup: npm ci && pip install lizard semgrep
      skip: ${{ github.event_name == 'pull_request' && 'mutation' || '' }}   # mutants are slow: nightly
    secrets:
      plugin_token: ${{ secrets.PLUGINS_TOKEN }}   # only if this repo is private
```

Locally, `gates.local_ci: true` makes the Code gate run the same checks; `run_gate.py ci` runs them on demand. Complexity and CRAP are judged on the functions the branch changed (`gates.ci_scope: changed`, the default; `all` checks the whole report), found by overlapping the `lizard` line ranges with the diff against the base branch. `gates.ci_skip` leaves a check out on purpose, for example `[mutation]`.

## Review policy (DDD)

`.sdlc/domain-map.yml` classifies paths as core, supporting or generic. `domain.py classify` puts the class of a change into the PR; `domain.py codeowners` generates CODEOWNERS so core paths need an owner's review; `domain.py checklist` lists the branch protection a human sets. Loosen or tighten `review_policy` by your production metrics (CFR, MTTR, MTTF): when they drop, tighten CI first, then review, then look at the phases.

## Development

```
python3 -m unittest discover -s plugins/sdlc/gates/tests -t plugins/sdlc/gates/tests
claude plugin validate .
```

Bump `version` in `.claude-plugin/plugin.json` and in the marketplace entry on every change.
