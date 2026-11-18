"""Hard CI before the PR: complexity, CRAP, mutation score, coverage, lint, SAST, DAST.
The stack runs its own tools (commands.*); the plugin reads two portable report formats:
complexity as `lizard --csv`, coverage as lcov or Cobertura XML, mutation as the mutation-testing-report-schema JSON (Stryker, PIT plugin, ...)."""

import csv
import json
import os
import re
import xml.etree.ElementTree as ET

import config
from checks import repo

CI_COMMANDS = ["lint", "coverage", "complexity", "mutation", "sast", "dast"]


def crap(ccn, cov):
    return ccn * ccn * (1 - cov) ** 3 + ccn


def read_lizard(path):
    """Rows of `lizard --csv`: nloc,ccn,token,param,length,location,file,function,long_name,start,end."""
    out = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 11 or not row[1].isdigit():
                continue
            out.append({"file": row[6], "function": row[7], "ccn": int(row[1]), "start": int(row[9]), "end": int(row[10])})
    return out


def read_lcov(path):
    hits, current = {}, None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("SF:"):
                current = hits.setdefault(line[3:], {})
            elif line.startswith("DA:") and current is not None:
                n, h = line[3:].split(",")[:2]
                current[int(n)] = current.get(int(n), 0) + int(h)
    return hits


def read_cobertura(path):
    hits = {}
    root = ET.parse(path).getroot()
    for cls in root.iter("class"):
        lines = hits.setdefault(cls.get("filename"), {})
        for line in cls.iter("line"):
            n = int(line.get("number"))
            lines[n] = lines.get(n, 0) + int(line.get("hits", "0"))
    return hits


def read_coverage(path):
    if path.endswith(".xml"):
        return read_cobertura(path)
    return read_lcov(path)


def _norm(p):
    return p.replace("\\", "/").lstrip("./")


def _lookup(hits, file):
    f = _norm(file)
    for k, v in hits.items():
        k2 = _norm(k)
        if k2 == f or k2.endswith("/" + f) or f.endswith("/" + k2):
            return v
    return None


def crap_rows(functions, hits):
    rows = []
    for fn in functions:
        lines = _lookup(hits, fn["file"])
        if lines is None:
            cov = 0.0
        else:
            span = [h for n, h in lines.items() if fn["start"] <= n <= fn["end"]]
            cov = (sum(1 for h in span if h > 0) / len(span)) if span else 0.0
        rows.append(dict(fn, coverage=cov, crap=crap(fn["ccn"], cov)))
    return sorted(rows, key=lambda r: -r["crap"])


def mutation_score(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    detected = undetected = 0
    for info in (data.get("files") or {}).values():
        for m in info.get("mutants", []):
            s = m.get("status")
            if s in ("Killed", "Timeout"):
                detected += 1
            elif s in ("Survived", "NoCoverage"):
                undetected += 1
    total = detected + undetected
    return (100.0 * detected / total) if total else None, total


def _report(cfg, name):
    p = (cfg.get("reports") or {}).get(name)
    if not p:
        return None
    return p if os.path.isabs(p) else os.path.join(cfg["_root"], p)


def _rel(path):
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def changed_ranges(root, base):
    """New-file line ranges the branch changed, per path: {path: [(first, last), ...]}; None when the diff cannot be computed."""
    mb = repo.merge_base(root, base)
    if mb is None:
        return None
    rc, out, _ = repo.sh(["git", "diff", "-U0", "--no-renames", mb, "HEAD", "--", "."], root)
    if rc != 0:
        return None
    ranges, path = {}, None
    for line in out.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@") and path:
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                start, count = int(m.group(1)), int(m.group(2)) if m.group(2) is not None else 1
                if count > 0:
                    ranges.setdefault(path, []).append((start, start + count - 1))
    return ranges


def touches(fn, ranges):
    """True when a function of the lizard report overlaps a line the branch added or changed."""
    f = _rel(fn["file"])
    for path, spans in ranges.items():
        if f == path or f.endswith("/" + path) or path.endswith("/" + f):
            return any(first <= fn["end"] and last >= fn["start"] for first, last in spans)
    return False


def check(cfg, skip=()):
    errors, root, th = [], cfg["_root"], cfg["thresholds"]
    for name in CI_COMMANDS:
        cmd = config.command(cfg, name)
        if cmd is None or cmd.strip().lower() == "none" or name in skip:
            continue
        rc, out = repo.run_command(cmd, root)
        if rc != 0:
            errors.append("ci `%s` (%s) failed, exit %d:\n%s" % (name, cmd, rc, repo.tail(out)))
    comp_path, cov_path = _report(cfg, "complexity"), _report(cfg, "coverage")
    if th.get("complexity_max") is not None or th.get("crap_max") is not None:
        if not comp_path or not os.path.exists(comp_path):
            errors.append("complexity/CRAP threshold set but reports.complexity (lizard --csv) is missing")
        else:
            functions = read_lizard(comp_path)
            if (cfg["gates"].get("ci_scope") or "changed") == "changed":
                ranges = changed_ranges(root, cfg["project"]["base_branch"])
                if ranges is None:
                    errors.append("cannot compute the diff against %s to scope complexity to the change: run `git fetch origin %s`" % (cfg["project"]["base_branch"], cfg["project"]["base_branch"]))
                    functions = []
                else:
                    functions = [fn for fn in functions if touches(fn, ranges)]
            if th.get("complexity_max") is not None:
                for fn in functions:
                    if fn["ccn"] > th["complexity_max"]:
                        errors.append("%s:%d %s cyclomatic complexity %d > %d" % (fn["file"], fn["start"], fn["function"], fn["ccn"], th["complexity_max"]))
            if th.get("crap_max") is not None:
                if not cov_path or not os.path.exists(cov_path):
                    errors.append("crap_max set but reports.coverage (lcov or Cobertura) is missing")
                else:
                    for r in crap_rows(functions, read_coverage(cov_path)):
                        if r["crap"] > th["crap_max"]:
                            errors.append("%s:%d %s CRAP %.1f > %s (ccn %d, coverage %.0f%%): lower complexity or add tests"
                                          % (r["file"], r["start"], r["function"], r["crap"], th["crap_max"], r["ccn"], 100 * r["coverage"]))
    if th.get("mutation_score_min") is not None and "mutation" not in skip:
        mpath = _report(cfg, "mutation")
        if not mpath or not os.path.exists(mpath):
            errors.append("mutation_score_min set but reports.mutation (mutation-testing-report JSON) is missing")
        else:
            score, total = mutation_score(mpath)
            if score is None:
                errors.append("mutation report has no mutants")
            elif score < th["mutation_score_min"]:
                errors.append("mutation score %.1f%% of %d mutants < %s%%: surviving mutants mean the tests do not check that code" % (score, total, th["mutation_score_min"]))
    return errors
