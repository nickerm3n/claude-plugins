# claude-plugins

Claude Code marketplace (`nickerm3n-plugins`) for your repositories.

| Plugin | What it does |
| --- | --- |
| [railguards](plugins/railguards) | Pre-push gate: keeps pull requests small, in scope and safe. |
| [sdlc](plugins/sdlc) | AI SDLC pipeline: Jira task → enrich → research → design → QA plan → plan → code → QA check → deploy → QA, with a gate between every phase. |

## Use in a project

`.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "nickerm3n-plugins": { "source": { "source": "github", "repo": "nickerm3n/claude-plugins" } }
  },
  "enabledPlugins": { "railguards@nickerm3n-plugins": true }
}
```

## Add a plugin

1. Create `plugins/<name>/` with `.claude-plugin/plugin.json` and any of `skills/`, `hooks/hooks.json`, `agents/`, `commands/`.
2. List it in `.claude-plugin/marketplace.json`.
3. Run `claude plugin validate .`.
4. Bump `version` in the plugin's `plugin.json` and in `marketplace.json` on every change. Projects pick a change up only after a version bump.

Plugins are for rules that are the same in every repository. Rules that belong to one repository (its stack practices, its railguards) stay in that repository's `.claude/`.
