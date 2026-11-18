---
description: Run the bugfix pipeline for a Jira issue (phase set defined by the project in pipelines.bugfix)
argument-hint: "<JIRA-KEY> [--dry-run]"
---

# /sdlc:bugfix

The video says bugfixes need a different phase set but does not show it, so the plugin ships none. The project defines it.

1. Read `.sdlc/config.yml`. If `pipelines.bugfix` is not defined, stop and say so: suggest the engineer adds e.g. `bugfix: [task, enrich, research, plan, code, qa-check, qa]` (our suggestion, not the author's) and runs the command again. Do not run a default.
2. Otherwise invoke the `sdlc:orchestrator` skill with pipeline `bugfix` and `$ARGUMENTS`.
