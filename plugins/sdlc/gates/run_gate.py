"""Deterministic gate. 0 tokens: it reads files, git, gh and runs the project's commands from .sdlc/config.yml.

  run_gate.py <phase> [--key K]          gate of a phase (task ... qa). deploy and qa run their command and write the artifact.
  run_gate.py approval <phase> [--key K] is the human approval for <phase> in place (design: label on the PR, or state)
  run_gate.py judge <phase> [--key K]    validate the judge report of <phase> and print the verdict
  run_gate.py ci [--skip mutation,dast]  hard CI: complexity, CRAP, mutation, coverage, lint, SAST, DAST from config
  run_gate.py crap --complexity <lizard.csv> --coverage <lcov|cobertura.xml> [--max N] [--top 20]
  run_gate.py plan-phases [--key K]      list the implementation phases of 06-plan.md
  run_gate.py hook                       SubagentStop hook (stdin JSON): block a phase agent until its gate passes

Exit: 0 pass, 1 fail, 2 usage/config error, 3 judge found a design issue.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
import state  # noqa: E402
from checks import phases, quality, repo  # noqa: E402

AGENT_PHASE = {
    "researcher": "research",
    "designer": "design",
    "qa-planner": "qa-plan",
    "planner": "plan",
    "coder": "code",
    "qa-checker": "qa-check",
}
JUDGES = ("judge-artifact", "judge-architecture")


def judge_report_path(cfg, run, phase):
    d = config.run_dir(cfg, run["key"])
    if phase == "code":
        return os.path.join(d, "judge-code-step-%s.md" % (run.get("plan_step") or 1))
    return os.path.join(d, "judge-%s.md" % phase)


def gate(cfg, key, phase, run=None):
    """Returns (errors, note)."""
    run = run or state.load(cfg, key)
    if phase == "code":
        return phases.check_code(cfg, key, run), None
    if phase in ("deploy", "qa"):
        cmd_name = "deploy" if phase == "deploy" else "e2e"
        errors, out = phases.check_command_phase(cfg, cmd_name, key, run)
        cmd = config.command(cfg, cmd_name) or "none"
        result = "skipped (commands.%s is none)" % cmd_name if out and out.startswith("skipped") else ("FAIL" if errors else "PASS")
        text = "# %s · %s\n\n## Result\n\n%s: `%s`\n\n## Output (tail)\n\n```text\n%s\n```\n" % (
            phase.upper(), key, result, cmd, repo.tail(out or "\n".join(errors), 60))
        with open(phases.artifact_path(cfg, key, phase), "w", encoding="utf-8") as f:
            f.write(text)
        return errors, result
    return phases.check_artifact(cfg, key, phase), None


def print_result(phase, errors, note=None):
    if errors:
        print("FAIL %s: %d violation(s)" % (phase, len(errors)))
        for i, e in enumerate(errors, 1):
            print("%d. %s" % (i, e))
        return 1
    print("PASS %s%s" % (phase, (" · " + note) if note else ""))
    return 0


def hook(stdin):
    try:
        data = json.loads(stdin or "{}")
    except ValueError:
        return 0
    agent = (data.get("agent_type") or "").split(":")[-1]
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    cfg_path = os.path.join(root, ".sdlc", "config.yml")
    if not os.path.exists(cfg_path) or (agent not in AGENT_PHASE and agent not in JUDGES):
        return 0
    try:
        cfg = config.load(cfg_path)
        key = state.current_key(cfg)
        run = state.load(cfg, key)
    except (config.ConfigError, SystemExit):
        return 0
    if run["status"] != "running":
        return 0
    phase = run["current"]
    if agent in JUDGES:
        verdict, errors = phases.check_judge(judge_report_path(cfg, run, phase))
        if not errors:
            return 0
        reason = "The judge report is not valid:\n- " + "\n- ".join(errors)
        print(json.dumps({"decision": "block", "reason": reason}))
        return 0
    if AGENT_PHASE[agent] != phase:
        return 0
    errors, _ = gate(cfg, key, phase, run)
    state.record(cfg, run, phase, "code", "fail" if errors else "pass", "%d violation(s)" % len(errors) if errors else None)
    if not errors:
        return 0
    if not state.fail(cfg, run, phase, "; ".join(e.splitlines()[0] for e in errors)):
        return 0
    reason = "Deterministic gate for phase `%s` failed (retry %d/%d). Fix every violation in place, then finish again:\n- %s" % (
        phase, run["retries"][phase], cfg["gates"]["max_retries"], "\n- ".join(errors))
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["hook"]:
        return hook(sys.stdin.read())
    ap = argparse.ArgumentParser(prog="run_gate.py")
    ap.add_argument("--config", default=".sdlc/config.yml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for ph in phases.ARTIFACTS:
        p = sub.add_parser(ph)
        p.add_argument("--key")
    for name in ("approval", "judge"):
        p = sub.add_parser(name)
        p.add_argument("phase")
        p.add_argument("--key")
    p = sub.add_parser("ci")
    p.add_argument("--skip", default="", help="comma-separated CI commands to skip, e.g. mutation")
    p = sub.add_parser("crap")
    p.add_argument("--complexity", required=True)
    p.add_argument("--coverage", required=True)
    p.add_argument("--max", type=float)
    p.add_argument("--top", type=int, default=20)
    p = sub.add_parser("plan-phases")
    p.add_argument("--key")
    a = ap.parse_args(argv)

    if a.cmd == "crap":
        rows = quality.crap_rows(quality.read_lizard(a.complexity), quality.read_coverage(a.coverage))
        for r in rows[: a.top]:
            print("%8.1f  ccn %-3d cov %3.0f%%  %s:%d %s" % (r["crap"], r["ccn"], 100 * r["coverage"], r["file"], r["start"], r["function"]))
        if a.max is not None:
            bad = [r for r in rows if r["crap"] > a.max]
            print("%d function(s) over CRAP %s" % (len(bad), a.max))
            return 1 if bad else 0
        return 0
    try:
        cfg = config.load(a.config)
    except config.ConfigError as e:
        print("config error: %s" % e)
        return 2
    if a.cmd == "ci":
        return print_result("ci", quality.check(cfg, [x.strip() for x in a.skip.split(",") if x.strip()]))
    key = state.current_key(cfg, getattr(a, "key", None))
    run = state.load(cfg, key)
    if a.cmd == "approval":
        return print_result("approval " + a.phase, phases.check_approval(cfg, key, run, a.phase))
    if a.cmd == "judge":
        verdict, errors = phases.check_judge(judge_report_path(cfg, run, a.phase))
        if errors:
            return print_result("judge " + a.phase, errors)
        state.record(cfg, run, a.phase, "judge", verdict, "step %s" % run.get("plan_step") if a.phase == "code" and run.get("plan_step") else None)
        print("VERDICT %s %s" % (a.phase, verdict))
        return {"PASS": 0, "FAIL": 1, "DESIGN_ISSUE": 3}[verdict]
    if a.cmd == "plan-phases":
        for i, t in enumerate(phases.plan_phases(cfg, key), 1):
            print("%d\t%s" % (i, t))
        return 0
    errors, note = gate(cfg, key, a.cmd, run)
    state.record(cfg, run, a.cmd, "code", "fail" if errors else "pass", "%d violation(s)" % len(errors) if errors else note)
    return print_result(a.cmd, errors, note)


if __name__ == "__main__":
    sys.exit(main())
