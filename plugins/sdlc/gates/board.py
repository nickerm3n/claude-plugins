"""The board: .sdlc/runs/index.html, one self-contained page (no network) that shows every run, its phase and gate history.
Re-rendered by state.py on every change; the page reloads itself every 5 seconds while a run is live.

  board.py [--config .sdlc/config.yml] [--open]
"""

import argparse
import html
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402

LABELS = {
    "task": "Task", "enrich": "Enrich", "research": "Research", "design": "Design", "qa-plan": "QA Plan",
    "plan": "Plan", "code": "Code", "qa-check": "QA Check", "deploy": "Deploy", "qa": "QA",
}
HUMAN = {"enrich", "design"}
ARTIFACT = {
    "task": "01-task.md", "enrich": "02-enrich.md", "research": "03-research.md", "design": "04-design.md",
    "qa-plan": "05-qa-plan.md", "plan": "06-plan.md", "code": "07-code.md", "qa-check": "08-qa-check.md",
    "deploy": "09-deploy.md", "qa": "10-qa.md",
}
STATUS_TEXT = {"running": "running", "waiting_human": "waiting for human", "escalated": "escalated", "done": "done"}

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e3e3de;--ok:#1f7a4d;--ok-bg:#e3f3ea;--run:#1f5fbf;--run-bg:#e4edfb;
--wait:#9a6400;--wait-bg:#fbf0d9;--bad:#b42318;--bad-bg:#fbe4e1;--skip:#8a8a84;--skip-bg:#efefec}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1e1e1c;--ink:#ecece8;--muted:#a3a39c;--line:#33332f;--ok:#5cc391;--ok-bg:#163326;
--run:#7aa7f0;--run-bg:#18263d;--wait:#e3b04b;--wait-bg:#3a2d12;--bad:#f0857a;--bad-bg:#3d1c18;--skip:#8a8a84;--skip-bg:#262624}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}h1{font-size:20px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 20px}
.run{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:16px}
.head{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;margin-bottom:12px}.key{font-weight:650;font-size:16px}
.badge{border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600}.meta{color:var(--muted);font-size:13px}
.track{display:grid;grid-template-columns:repeat(auto-fit,minmax(92px,1fr));gap:6px}
.ph{border-radius:8px;padding:8px;border:1px solid var(--line);min-height:62px}.ph b{display:block;font-size:13px}.ph small{color:var(--muted);font-size:11px;display:block}
.ph a{color:inherit}.cur{outline:2px solid var(--run);outline-offset:1px}
.s-passed{background:var(--ok-bg);color:var(--ok)}.s-running,.s-retry{background:var(--run-bg);color:var(--run)}.s-waiting{background:var(--wait-bg);color:var(--wait)}
.s-escalated{background:var(--bad-bg);color:var(--bad)}.s-skipped{background:var(--skip-bg);color:var(--skip)}.s-pending{background:transparent;color:var(--muted)}
.b-running{background:var(--run-bg);color:var(--run)}.b-waiting_human{background:var(--wait-bg);color:var(--wait)}.b-escalated{background:var(--bad-bg);color:var(--bad)}.b-done{background:var(--ok-bg);color:var(--ok)}
details{margin-top:12px}summary{cursor:pointer;color:var(--muted)}table{border-collapse:collapse;width:100%;margin-top:8px;font-size:12.5px}
td{border-top:1px solid var(--line);padding:5px 8px 5px 0;vertical-align:top}td.t{white-space:nowrap;color:var(--muted)}pre{margin:0;white-space:pre-wrap;font:12px ui-monospace,Menlo,monospace}
.empty{color:var(--muted);padding:32px;text-align:center;border:1px dashed var(--line);border-radius:10px}
"""


def _e(s):
    return html.escape(str(s if s is not None else ""))


def _phase_cell(run, phase, base):
    st = run["phase_status"].get(phase, "pending")
    cur = " cur" if phase == run["current"] and run["status"] != "done" else ""
    notes = []
    if phase in HUMAN:
        notes.append("human in loop")
    if run["retries"].get(phase):
        notes.append("retry %d" % run["retries"][phase])
    if phase in run.get("approvals", {}):
        notes.append("✓ %s" % run["approvals"][phase]["by"])
    if phase == "code" and run.get("plan_step") and phase == run["current"]:
        notes.append("step %s" % run["plan_step"])
    name = _e(LABELS.get(phase, phase))
    art = os.path.join(base, ARTIFACT[phase])
    if os.path.exists(art):
        name = '<a href="%s/%s">%s</a>' % (_e(run["key"]), ARTIFACT[phase], name)
    return '<div class="ph s-%s%s"><b>%s</b><small>%s</small><small>%s</small></div>' % (
        _e(st), cur, name, _e(st), _e(" · ".join(notes)))


def _run_card(cfg, run):
    base = config.run_dir(cfg, run["key"])
    cells = "".join(_phase_cell(run, p, base) for p in run["phases"])
    pr = ' · <a href="%s">PR</a>' % _e(run["pr"]) if run.get("pr") else ""
    jira = (cfg.get("tracker") or {}).get("base_url")
    key = '<a href="%s/browse/%s">%s</a>' % (_e(jira.rstrip("/")), _e(run["key"]), _e(run["key"])) if jira else _e(run["key"])
    rows = "".join(
        '<tr><td class="t">%s</td><td>%s</td><td>%s%s</td><td><pre>%s</pre></td></tr>'
        % (_e(e["at"].replace("T", " ").rstrip("Z")), _e(LABELS.get(e["phase"], e["phase"])), _e(e["event"]),
           (" · " + _e(e["by"])) if e.get("by") else "", _e(e.get("detail", "")))
        for e in reversed(run.get("history", [])[-40:]))
    return """<section class="run"><div class="head"><span class="key">%s</span>
<span class="badge b-%s">%s</span><span class="meta">%s · %s%s%s · updated %s</span></div>
<div class="track">%s</div><details><summary>Gate history (%d events)</summary><table>%s</table></details></section>""" % (
        key, _e(run["status"]), _e(STATUS_TEXT.get(run["status"], run["status"])), _e(run["pipeline"]),
        _e(run.get("branch") or "no branch"), " · dry-run" if run.get("dry_run") else "", pr,
        _e(run.get("updated_at", "").replace("T", " ").rstrip("Z")), cells, len(run.get("history", [])), rows)


def render(cfg):
    import state

    runs = sorted(state.all_runs(cfg), key=lambda r: (r["status"] == "done", r.get("updated_at", "")), reverse=False)
    live = [r for r in runs if r["status"] != "done"]
    done = [r for r in runs if r["status"] == "done"]
    live.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    body = "".join(_run_card(cfg, r) for r in live + done) or '<div class="empty">No runs yet. Start one with <code>/sdlc:feature PROJ-123</code>.</div>'
    refresh = '<meta http-equiv="refresh" content="5">' if live else ""
    name = (cfg.get("project") or {}).get("name") or "project"
    page = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">%s
<title>SDLC Runs</title><style>%s</style></head><body><main><h1>AI SDLC · %s</h1>
<p class="sub">%d active, %d done. Generated by the sdlc plugin from .sdlc/runs/*/run.json; do not edit.</p>%s</main></body></html>
""" % (refresh, CSS, _e(name), len(live), len(done), body)
    out = os.path.join(state.runs_root(cfg), "index.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="board.py")
    ap.add_argument("--config", default=".sdlc/config.yml")
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args(argv)
    out = render(config.load(a.config))
    print(out)
    if a.open:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([opener, out], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
