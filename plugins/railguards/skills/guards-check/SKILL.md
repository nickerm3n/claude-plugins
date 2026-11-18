---
name: guards-check
description: Highlight when a diff touches a railguard (session, payments, navigation, native build, CI, config, dependencies, schema) and require the developer's explicit confirmation before push. Use as a step of the gate pipeline or whenever a change reaches a shared or sensitive area.
---

# Guards check

Railguards are the parts of the codebase where a small edit has a large or irreversible effect. They are listed, with the reason for each, in `.claude/railguards.conf`. The hook already flags path matches; this skill adds the thinking the glob cannot do.

## Method

1. Run `bash "${CLAUDE_PLUGIN_ROOT}/hooks/gate.sh" status` and read the "Railguards touched" list.
2. Also look for guarded behaviour the globs miss: a change in a file outside the list that alters a session gate, a permission check, a price or fee, a charge or payment call, a GraphQL contract, a migration or entity, an env var, a build setting, or something every screen imports. Treat those as hits too.
3. For each hit, say in the report:
   - **what** was edited, in one line
   - **who inherits it**: the screens, resolvers or jobs that use the edited code even though their files are not in the diff (open the callers, do not guess)
   - **what breaks if it is wrong**, and whether it can be rolled back (a Play upload, a migration and a charge cannot)
   - **why the task needs it**. If the task does not need it, the answer is to remove the change, not to confirm it.
4. Ask the developer to confirm each hit by name. "Yes, AuthContext and the sign-in screen are meant to change" counts. A general "ok" does not.
5. The hook blocks push until approval, and approval needs `--confirmed` with their answer. If they decline, remove the change.

## Do not

- Do not shrink a hit by editing `railguards.conf`, adding an `ignore`, or splitting the same edit across commits. The gate looks at the whole diff against the base.
- Do not widen the check into a general code review. Style and naming are for ESLint and Prettier; deep review is the code-review skill.
