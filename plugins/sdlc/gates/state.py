"""Run state: .sdlc/runs/<KEY>/run.json. The orchestrator moves a run only through these commands, never by editing the file.

  state.py init <KEY> [--pipeline feature] [--dry-run] [--branch <name>]
  state.py show [<KEY>] [--json]
  state.py start <phase> [--key K]               the phase agent is about to run
  state.py pass <phase> [--key K] [--note ...]   gate passed, move to the next phase
  state.py fail <phase> --reason ... [--key K]   gate failed, retry++ (exit 3 when over max_retries: escalate)
  state.py wait <phase> --reason ... [--key K]   stop for a human
  state.py approve <phase> --by <name> [--key K] record a human approval (Enrich, Design, escalations)
  state.py rewind <phase> --by <name> --reason ... [--key K]   human chose to go back (e.g. Code -> Design)
  state.py step <n> [--key K]                    current plan phase during Code
  state.py set-pr <url> [--key K]
  state.py list [--json]
Every change re-renders .sdlc/runs/index.html (the board).
"""

import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402

JIRA_KEY = re.compile(r"[A-Z][A-Z0-9]+-\d+")


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def runs_root(cfg):
    return os.path.join(cfg["_root"], cfg["paths"]["runs"])


def path_for(cfg, key):
    return os.path.join(config.run_dir(cfg, key), "run.json")


def load(cfg, key):
    p = path_for(cfg, key)
    if not os.path.exists(p):
        raise SystemExit("no run for %s (%s). Start it with /sdlc:feature %s" % (key, p, key))
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(cfg, run):
    run["updated_at"] = now()
    p = path_for(cfg, run["key"])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(run, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)
    try:
        import board

        board.render(cfg)
    except Exception as e:  # the board is a view; a broken view must not stop the pipeline
        print("warning: board not rendered: %s" % e, file=sys.stderr)


def all_runs(cfg):
    root = runs_root(cfg)
    out = []
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name, "run.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def current_key(cfg, explicit=None):
    if explicit:
        return explicit
    from checks import repo

    br = repo.branch(cfg["_root"]) or ""
    m = JIRA_KEY.search(br)
    if m and os.path.exists(path_for(cfg, m.group(0))):
        return m.group(0)
    live = [r for r in all_runs(cfg) if r.get("status") not in ("done",)]
    if live:
        return max(live, key=lambda r: r.get("updated_at", ""))["key"]
    raise SystemExit("no active run: pass --key or check out the run's branch")


def event(run, phase, kind, detail=None, by=None):
    e = {"at": now(), "phase": phase, "event": kind}
    if detail:
        e["detail"] = detail
    if by:
        e["by"] = by
    run.setdefault("history", []).append(e)


def _expect_current(run, phase):
    if run["current"] != phase:
        raise SystemExit("run %s is at `%s`, not `%s`" % (run["key"], run["current"], phase))


HUMAN_PHASES = ("enrich", "design")


def gate_plan(cfg, phases):
    """Which gate steps each phase has: code always, a judge where configured, a human on Enrich, Design and a merge-deploy."""
    plan = {}
    for p in phases:
        steps = ["code"]
        if (cfg.get("judges") or {}).get(p):
            steps.append("judge")
        if p in HUMAN_PHASES or (p == "deploy" and cfg["human"].get("merge_before_deploy")):
            steps.append("human")
        plan[p] = steps
    return plan


def ensure_gates(cfg, run):
    if "gate_plan" not in run:
        run["gate_plan"] = gate_plan(cfg, run["phases"])
    gates = run.setdefault("gates", {})
    for p, steps in run["gate_plan"].items():
        g = gates.setdefault(p, {})
        for step in steps:
            g.setdefault(step, {"status": "pending"})
    return run


def record(cfg, run, phase, step, status, detail=None):
    """Result of one gate step, for the board and the pane: code pass/fail, judge PASS/FAIL/DESIGN_ISSUE, human waiting/approved."""
    ensure_gates(cfg, run)
    if step not in run["gate_plan"].get(phase, []):
        return
    entry = {"status": status, "at": now()}
    if detail:
        entry["detail"] = detail
    run["gates"][phase][step] = entry
    save(cfg, run)


def init(cfg, key, pipeline, dry_run, branch):
    if not JIRA_KEY.fullmatch(key):
        raise SystemExit("`%s` is not a Jira key (e.g. PROJ-123)" % key)
    if pipeline not in cfg["pipelines"]:
        raise SystemExit("pipeline `%s` is not defined in .sdlc/config.yml (pipelines.%s)" % (pipeline, pipeline))
    if os.path.exists(path_for(cfg, key)):
        raise SystemExit("run %s already exists; use `state.py show %s`" % (key, key))
    phases = list(cfg["pipelines"][pipeline])
    run = {
        "version": 1,
        "key": key,
        "pipeline": pipeline,
        "phases": phases,
        "current": phases[0],
        "status": "running",
        "dry_run": bool(dry_run),
        "branch": branch,
        "pr": None,
        "plan_step": None,
        "retries": {},
        "approvals": {},
        "phase_status": {p: "pending" for p in phases},
        "created_at": now(),
        "history": [],
    }
    ensure_gates(cfg, run)
    event(run, phases[0], "init", "pipeline %s%s" % (pipeline, ", dry-run" if dry_run else ""))
    save(cfg, run)
    return run


def start(cfg, run, phase):
    _expect_current(run, phase)
    if run["status"] in ("waiting_human", "escalated"):
        raise SystemExit("run %s is %s at %s: a human has to decide first (approve / rewind)" % (run["key"], run["status"], phase))
    run["phase_status"][phase] = "running"
    event(run, phase, "start")
    save(cfg, run)


def advance(cfg, run, phase, note=None):
    _expect_current(run, phase)
    run["phase_status"][phase] = "passed"
    event(run, phase, "pass", note)
    ensure_gates(cfg, run)
    human = run["gates"].get(phase, {}).get("human")
    if human and human["status"] != "approved":
        run["gates"][phase]["human"] = {"status": "approved", "at": now(), "detail": note or "confirmed"}
    phases = run["phases"]
    i = phases.index(phase)
    nxt = None
    for p in phases[i + 1 :]:
        if run["dry_run"] and p in ("code", "qa-check", "deploy", "qa"):
            run["phase_status"][p] = "skipped"
            continue
        nxt = p
        break
    if nxt is None:
        run["status"] = "done"
        event(run, phase, "done")
    else:
        run["current"] = nxt
        run["status"] = "running"
    save(cfg, run)
    return nxt


def fail(cfg, run, phase, reason):
    _expect_current(run, phase)
    n = run["retries"].get(phase, 0) + 1
    run["retries"][phase] = n
    limit = cfg["gates"]["max_retries"]
    if n > limit:
        run["status"] = "escalated"
        run["phase_status"][phase] = "escalated"
        event(run, phase, "escalate", "retry %d > max_retries %d: %s" % (n, limit, reason))
        save(cfg, run)
        return False
    run["phase_status"][phase] = "retry"
    event(run, phase, "fail", "retry %d/%d: %s" % (n, limit, reason))
    save(cfg, run)
    return True


def wait(cfg, run, phase, reason):
    _expect_current(run, phase)
    run["status"] = "waiting_human"
    run["phase_status"][phase] = "waiting"
    event(run, phase, "wait", reason)
    ensure_gates(cfg, run)
    if "human" in run["gate_plan"].get(phase, []):
        run["gates"][phase]["human"] = {"status": "waiting", "at": now(), "detail": reason}
    save(cfg, run)


def approve(cfg, run, phase, by):
    run["approvals"][phase] = {"by": by, "at": now()}
    if run["current"] == phase and run["status"] in ("waiting_human", "escalated"):
        run["status"] = "running"
        run["retries"][phase] = 0
        run["phase_status"][phase] = "running"
    event(run, phase, "approve", by=by)
    ensure_gates(cfg, run)
    if "human" in run["gate_plan"].get(phase, []):
        run["gates"][phase]["human"] = {"status": "approved", "at": now(), "detail": by}
    save(cfg, run)


def rewind(cfg, run, phase, by, reason):
    phases = run["phases"]
    if phase not in phases or phases.index(phase) > phases.index(run["current"]):
        raise SystemExit("can only rewind to an earlier phase of this run")
    ensure_gates(cfg, run)
    for p in phases[phases.index(phase) :]:
        run["gates"][p] = {step: {"status": "pending"} for step in run["gate_plan"].get(p, [])}
        run["phase_status"][p] = "pending"
        run["retries"].pop(p, None)
        run["approvals"].pop(p, None)
    run["current"] = phase
    run["status"] = "running"
    run["plan_step"] = None
    event(run, phase, "rewind", reason, by=by)
    save(cfg, run)


def summary(run):
    phases = run["phases"]
    cur = run["current"]
    pos = phases.index(cur) + 1
    status = {"running": "", "waiting_human": " ⏸ waiting for human", "escalated": " ⛔ escalated", "done": " ✓ done"}[run["status"]]
    step = " step %s" % run["plan_step"] if run.get("plan_step") and cur == "code" else ""
    retry = run["retries"].get(cur, 0)
    retry_s = " retry %d" % retry if retry else ""
    return "%s ▸ %s %d/%d%s%s%s" % (run["key"], cur, pos, len(phases), step, retry_s, status)


def show(run, as_json):
    if as_json:
        print(json.dumps(run, indent=2, ensure_ascii=False))
        return
    print(summary(run))
    marks = {"pending": "·", "running": "▶", "retry": "↻", "waiting": "⏸", "passed": "✓", "skipped": "–", "escalated": "⛔"}
    for p in run["phases"]:
        st = run["phase_status"].get(p, "pending")
        extra = []
        if run["retries"].get(p):
            extra.append("retries %d" % run["retries"][p])
        if p in run["approvals"]:
            extra.append("approved by %s" % run["approvals"][p]["by"])
        print("  %s %-9s %s%s" % (marks.get(st, "?"), p, st, ("  (" + ", ".join(extra) + ")") if extra else ""))
    if run.get("pr"):
        print("PR: %s" % run["pr"])
    last = run["history"][-3:]
    if last:
        print("Last events:")
        for e in last:
            print("  %s %s %s %s" % (e["at"], e["phase"], e["event"], e.get("detail", "").splitlines()[0] if e.get("detail") else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="state.py")
    ap.add_argument("--config", default=".sdlc/config.yml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("key")
    p.add_argument("--pipeline", default="feature")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--branch")
    p = sub.add_parser("show")
    p.add_argument("key", nargs="?")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("list")
    p.add_argument("--json", action="store_true")
    for name in ("start", "pass", "fail", "wait", "approve", "rewind"):
        p = sub.add_parser(name)
        p.add_argument("phase")
        p.add_argument("--key")
        p.add_argument("--reason")
        p.add_argument("--note")
        p.add_argument("--by")
    p = sub.add_parser("step")
    p.add_argument("n", type=int)
    p.add_argument("--key")
    p = sub.add_parser("set-pr")
    p.add_argument("url")
    p.add_argument("--key")
    a = ap.parse_args(argv)
    try:
        cfg = config.load(a.config)
    except config.ConfigError as e:
        raise SystemExit(str(e))

    if a.cmd == "init":
        show(init(cfg, a.key, a.pipeline, a.dry_run, a.branch), False)
        return 0
    if a.cmd == "list":
        runs = all_runs(cfg)
        if a.json:
            print(json.dumps(runs, indent=2, ensure_ascii=False))
        else:
            for r in runs:
                print(summary(r))
            if not runs:
                print("no runs")
        return 0
    run = load(cfg, current_key(cfg, getattr(a, "key", None)))
    if a.cmd == "show":
        show(run, a.json)
    elif a.cmd == "start":
        start(cfg, run, a.phase)
    elif a.cmd == "pass":
        nxt = advance(cfg, run, a.phase, a.note)
        print("next: %s" % (nxt or "done"))
    elif a.cmd == "fail":
        if not a.reason:
            raise SystemExit("--reason is required")
        if not fail(cfg, run, a.phase, a.reason):
            print("ESCALATE: %s failed its gate more than %d times. Stop and ask the engineer." % (a.phase, cfg["gates"]["max_retries"]))
            return 3
        print("retry %d/%d" % (run["retries"][a.phase], cfg["gates"]["max_retries"]))
    elif a.cmd == "wait":
        if not a.reason:
            raise SystemExit("--reason is required")
        wait(cfg, run, a.phase, a.reason)
    elif a.cmd == "approve":
        if not a.by:
            raise SystemExit("--by <engineer> is required: only a human approves")
        approve(cfg, run, a.phase, a.by)
    elif a.cmd == "rewind":
        if not a.by or not a.reason:
            raise SystemExit("--by and --reason are required: only a human rewinds")
        rewind(cfg, run, a.phase, a.by, a.reason)
    elif a.cmd == "step":
        run["plan_step"] = a.n
        event(run, "code", "step", "plan phase %d" % a.n)
        save(cfg, run)
    elif a.cmd == "set-pr":
        run["pr"] = a.url
        event(run, run["current"], "pr", a.url)
        save(cfg, run)
    if a.cmd != "show":
        print(summary(run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
