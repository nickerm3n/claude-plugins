"""Gate per phase. Section names, diagram kinds and limits are our decisions (the video does not give them);
a project can override sections and diagrams per phase under `artifacts.<phase>` in .sdlc/config.yml."""

import os
import re

import config
from checks import markdown, mermaid, repo, quality

JIRA_KEY = r"[A-Z][A-Z0-9]+-\d+"
QA_ID = r"\bQA-\d+\b"

ARTIFACTS = {
    "task": "01-task.md",
    "enrich": "02-enrich.md",
    "research": "03-research.md",
    "design": "04-design.md",
    "qa-plan": "05-qa-plan.md",
    "plan": "06-plan.md",
    "code": "07-code.md",
    "qa-check": "08-qa-check.md",
    "deploy": "09-deploy.md",
    "qa": "10-qa.md",
}

SPECS = {
    "task": {"sections": ["Summary", "Acceptance criteria"], "non_empty": ["Summary", "Acceptance criteria"]},
    "enrich": {
        "sections": ["Engineer's view", "Decisions", "Constraints", "Pitfalls", "Open questions"],
        "non_empty": ["Engineer's view", "Decisions", "Constraints"],
    },
    "research": {
        "sections": ["Scope", "Relevant code", "Knowledge base", "Constraints", "Risks"],
        "non_empty": ["Scope", "Relevant code", "Risks"],
        "refs": True,
    },
    "design": {
        "sections": ["Context", "Containers and components", "Sequence", "Data flow", "Decisions", "Risks"],
        "non_empty": ["Context", "Containers and components", "Sequence", "Data flow", "Decisions"],
        "diagrams": ["c4", "sequence", "dfd"],
    },
    "qa-plan": {
        "sections": ["Contracts", "Scenarios", "Tests to add or change"],
        "non_empty": ["Contracts", "Scenarios", "Tests to add or change"],
        "qa_ids": True,
    },
    "plan": {"sections": ["Phases"], "non_empty": ["Phases"], "no_code": True},
    "code": {"sections": ["Steps"], "non_empty": ["Steps"]},
    "qa-check": {"sections": ["Contract changes", "Scenario status"], "non_empty": ["Scenario status"]},
    "deploy": {"sections": ["Result"], "non_empty": ["Result"]},
    "qa": {"sections": ["Result"], "non_empty": ["Result"]},
}


def spec(cfg, phase):
    s = dict(SPECS[phase])
    override = (cfg.get("artifacts") or {}).get(phase) or {}
    for k in ("sections", "non_empty", "diagrams"):
        if k in override:
            s[k] = override[k]
    return s


def artifact_path(cfg, key, phase):
    return os.path.join(config.run_dir(cfg, key), ARTIFACTS[phase])


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def check_artifact(cfg, key, phase):
    path = artifact_path(cfg, key, phase)
    if not os.path.exists(path):
        return ["artifact %s does not exist" % os.path.relpath(path, cfg["_root"])]
    text = read(path)
    s = spec(cfg, phase)
    errors = markdown.require_sections(text, s["sections"], s.get("non_empty", ()))
    limit = cfg["thresholds"]["plan_max_lines"] if phase == "plan" else cfg["thresholds"]["artifact_max_lines"]
    errors += markdown.max_lines(text, limit, ARTIFACTS[phase])
    if s.get("refs"):
        errors += markdown.refs_exist(text, cfg["_root"])
    if s.get("diagrams"):
        errors += mermaid.check(text, s["diagrams"])
    if s.get("qa_ids") and not markdown.ids(text, QA_ID):
        errors.append("no scenario ids: give every scenario an id like QA-1 so QA Check and QA can trace it")
    if s.get("no_code"):
        errors += markdown.code_fences(text)
    extra = PHASE_CHECKS.get(phase)
    if extra:
        errors += extra(cfg, key, text)
    return errors


def _task(cfg, key, text):
    if not re.search(r"^Key:\s*%s\s*$" % re.escape(key), text, re.M):
        return ["missing line `Key: %s` (the Jira issue this run is for)" % key]
    return []


def _plan(cfg, key, text):
    body = markdown.sections(text).get("phases", "")
    phases = re.split(r"^###\s+", body, flags=re.M)[1:]
    if not phases:
        return ["`## Phases` has no `### Phase N: <title>` entries"]
    errors = []
    for n, p in enumerate(phases, 1):
        title = p.splitlines()[0].strip()
        if not re.match(r"^Phase\s+\d+\s*:", title, re.I):
            errors.append("phase heading `### %s` must look like `### Phase %d: <title>`" % (title, n))
        if not re.search(r"^\s*(\*\*)?Goal:?(\*\*)?:?\s*\S", p, re.M | re.I):
            errors.append("`%s` has no `Goal:` line" % title)
        if not re.search(r"^\s*(\*\*)?Done when:?(\*\*)?:?\s*\S", p, re.M | re.I):
            errors.append("`%s` has no `Done when:` line" % title)
    return errors


def _qa_check(cfg, key, text):
    plan_path = artifact_path(cfg, key, "qa-plan")
    if not os.path.exists(plan_path):
        return ["05-qa-plan.md is missing: QA Check reconciles it with the code"]
    planned = markdown.ids(read(plan_path), QA_ID)
    status = markdown.sections(text).get("scenario status", "")
    missing = [i for i in planned if not re.search(r"\b%s\b" % re.escape(i), status)]
    if missing:
        return ["`## Scenario status` does not cover %s from 05-qa-plan.md" % ", ".join(missing)]
    return []


PHASE_CHECKS = {"task": _task, "plan": _plan, "qa-check": _qa_check}


def plan_phases(cfg, key):
    text = read(artifact_path(cfg, key, "plan"))
    body = markdown.sections(text).get("phases", "")
    return [p.splitlines()[0].strip() for p in re.split(r"^###\s+", body, flags=re.M)[1:]]


def _required_command(cfg, name):
    raw = (cfg.get("commands") or {}).get(name)
    if raw is not None and str(raw).strip().lower() == "none":
        return None, None
    cmd = config.command(cfg, name)
    if cmd is None:
        return None, "commands.%s is not set in .sdlc/config.yml (set it, or `none` to skip it on purpose)" % name
    return cmd, None


def check_code(cfg, key, run):
    root = cfg["_root"]
    base = cfg["project"]["base_branch"]
    runs = cfg["paths"]["runs"]
    errors = []
    data, err = repo.pr(root)
    if data is None:
        errors.append("no pull request for the current branch: %s" % err)
    elif data.get("state") != "OPEN":
        errors.append("pull request %s is %s, not OPEN" % (data.get("url"), data.get("state")))
    files = repo.changed_files(root, base, runs)
    if files is None:
        errors.append("cannot compute the diff against %s: run `git fetch origin %s`" % (base, base))
    elif not files:
        errors.append("no code changes outside %s/ against %s" % (runs, base))
    for pattern in cfg["gates"].get("forbidden_in_diff") or []:
        rx = re.compile(pattern)
        for path, line in repo.added_lines(root, base, runs):
            if rx.search(line):
                errors.append("%s: added line matches forbidden pattern `%s`: %s" % (path, pattern, line.strip()[:120]))
    for name in ("lint", "test"):
        cmd, err = _required_command(cfg, name)
        if err:
            errors.append(err)
            continue
        if cmd is None:
            continue
        rc, out = repo.run_command(cmd, root)
        if rc != 0:
            errors.append("`%s` failed (exit %d). Run the whole command, not a subset, and fix every failure:\n%s" % (cmd, rc, repo.tail(out)))
        elif name == "test":
            skipped = repo.skipped_count(out, cfg["gates"].get("skipped_tests_regex"))
            baseline = cfg["gates"].get("skipped_tests_baseline") or 0
            if skipped > baseline:
                errors.append("`%s` reports %d skipped test(s), the base branch has %d: un-skip the new ones or ask the engineer" % (cmd, skipped, baseline))
    if cfg["gates"].get("local_ci"):
        errors += quality.check(cfg, cfg["gates"].get("ci_skip") or [])
    return errors


def command_env(cfg, key, run, pr=None):
    """What a project's deploy / e2e script may need to know about the run."""
    return {
        "SDLC_KEY": key,
        "SDLC_RUN_DIR": config.run_dir(cfg, key),
        "SDLC_BRANCH": run.get("branch") if run else None,
        "SDLC_BASE": cfg["project"]["base_branch"],
        "SDLC_PR_URL": (pr or {}).get("url") or (run or {}).get("pr"),
        "SDLC_MERGE_SHA": (pr or {}).get("mergeCommit"),
    }


def check_command_phase(cfg, name, key=None, run=None):
    cmd, err = _required_command(cfg, name)
    if err:
        return [err], None
    if cmd is None:
        return [], "skipped: commands.%s is `none`" % name
    pr = None
    if name == "deploy" and cfg["human"].get("merge_before_deploy"):
        pr, perr = repo.pr(cfg["_root"], (run or {}).get("pr"))
        if pr is None:
            return ["merge_before_deploy is set but there is no pull request: %s" % perr], None
        if pr.get("state") != "MERGED":
            return ["waiting for the engineer: %s is %s; merge it into %s, CI deploys the merge" % (pr.get("url"), pr.get("state"), cfg["project"]["base_branch"])], None
    rc, out = repo.run_command(cmd, cfg["_root"], env=command_env(cfg, key, run, pr))
    if rc != 0:
        return ["`%s` failed (exit %d):\n%s" % (cmd, rc, repo.tail(out))], out
    return [], out


def check_approval(cfg, key, run, phase="design"):
    rule = cfg["human"].get("%s_approval" % phase) or "state"
    if rule.startswith("github-label:"):
        label = rule.split(":", 1)[1]
        data, err = repo.pr(cfg["_root"])
        if data is None:
            return ["no pull request to read the `%s` label from: %s" % (label, err)]
        if label not in data["labels"]:
            return ["waiting for the team: label `%s` is not on %s" % (label, data["url"])]
        return []
    if rule == "state":
        if not (run.get("approvals") or {}).get(phase):
            return ["waiting for the engineer: %s is not approved (state.py approve %s --by <name>)" % (phase, phase)]
        return []
    return ["unknown human.%s_approval rule `%s`" % (phase, rule)]


VERDICT = re.compile(r"^Verdict:\s*(PASS|FAIL|DESIGN_ISSUE)\s*$", re.M)


def check_judge(path):
    if not os.path.exists(path):
        return "MISSING", ["judge report %s does not exist" % path]
    text = read(path)
    m = VERDICT.findall(text)
    if len(m) != 1:
        return "MALFORMED", ["judge report must contain exactly one line `Verdict: PASS|FAIL|DESIGN_ISSUE`"]
    errors = markdown.require_sections(text, ["Findings"])
    if m[0] != "PASS" and not markdown.has_content(markdown.sections(text).get("findings", "")):
        errors.append("verdict is %s but `## Findings` is empty" % m[0])
    return m[0], errors
