"""Checks against the repository: git diff, GitHub PR, and the project's own commands from config."""

import json
import os
import re
import subprocess


def sh(args, cwd, timeout=60):
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", "%s: command not found" % args[0]
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %ds" % timeout


def branch(root):
    rc, out, _ = sh(["git", "symbolic-ref", "--short", "-q", "HEAD"], root)
    return out.strip() if rc == 0 else None


def merge_base(root, base):
    for ref in ("origin/" + base, base):
        rc, out, _ = sh(["git", "merge-base", ref, "HEAD"], root)
        if rc == 0:
            return out.strip()
    return None


def changed_files(root, base, exclude_prefix):
    mb = merge_base(root, base)
    if mb is None:
        return None
    rc, out, _ = sh(["git", "diff", "--name-only", "--no-renames", mb, "HEAD"], root)
    files = [f for f in out.splitlines() if f]
    return [f for f in files if not f.startswith(exclude_prefix.rstrip("/") + "/")]


def added_lines(root, base, exclude_prefix):
    mb = merge_base(root, base)
    if mb is None:
        return []
    rc, out, _ = sh(["git", "diff", "-U0", "--no-renames", mb, "HEAD", "--", ".", ":(exclude)%s" % exclude_prefix], root)
    result, path = [], None
    for line in out.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and path:
            result.append((path, line[1:]))
    return result


def pr(root, ref=None):
    """The PR of the current branch, or `ref` (a URL or number): needed after a merge, when the branch may be gone."""
    args = ["gh", "pr", "view"] + ([str(ref)] if ref else []) + ["--json", "url,number,isDraft,state,labels,headRefName,mergeCommit"]
    rc, out, err = sh(args, root)
    if rc != 0:
        return None, (err or out).strip()
    data = json.loads(out)
    data["labels"] = [l["name"] for l in data.get("labels", [])]
    data["mergeCommit"] = (data.get("mergeCommit") or {}).get("oid")
    return data, None


def run_command(cmd, root, timeout=3600, env=None):
    full_env = None
    if env:
        full_env = dict(os.environ)
        full_env.update({k: str(v) for k, v in env.items() if v is not None})
    try:
        p = subprocess.run(cmd, cwd=root, shell=True, capture_output=True, text=True, timeout=timeout, env=full_env)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ds" % timeout


def tail(text, n=30):
    lines = text.rstrip().splitlines()
    return "\n".join(lines[-n:])


def skipped_count(output, regex):
    if not regex:
        return 0
    total = 0
    for m in re.finditer(regex, output):
        try:
            total += int(m.group(1))
        except (IndexError, ValueError, TypeError):
            total += 1
    return total
