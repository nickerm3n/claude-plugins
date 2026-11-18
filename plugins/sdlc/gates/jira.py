"""Jira Cloud REST, stdlib only. Credentials come from the environment, never from config or the plugin:
JIRA_EMAIL and JIRA_API_TOKEN (and JIRA_BASE_URL, or tracker.base_url in .sdlc/config.yml).

  jira.py fetch <KEY> [--write]      print the issue as Markdown; --write saves it to .sdlc/runs/<KEY>/01-task.md
  jira.py comment <KEY> --file <md>  add a plain-text comment (escalations, design review link)
  jira.py check                      verify that credentials work

Without credentials the orchestrator falls back to the Atlassian MCP tools if they are connected, or asks the engineer to paste the issue.
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402

FIELDS = "summary,description,issuetype,status,priority,labels,components,parent,issuelinks,customfield_10016"


class JiraError(RuntimeError):
    pass


def _base(cfg):
    url = os.environ.get("JIRA_BASE_URL") or ((cfg or {}).get("tracker") or {}).get("base_url")
    if not url:
        raise JiraError("set JIRA_BASE_URL or tracker.base_url in .sdlc/config.yml")
    return url.rstrip("/")


def _auth():
    email, token = os.environ.get("JIRA_EMAIL"), os.environ.get("JIRA_API_TOKEN")
    if not email or not token:
        raise JiraError("set JIRA_EMAIL and JIRA_API_TOKEN in the environment (not in the repo)")
    return "Basic " + base64.b64encode(("%s:%s" % (email, token)).encode()).decode()


def request(cfg, method, path, body=None):
    req = urllib.request.Request(_base(cfg) + path, method=method)
    req.add_header("Authorization", _auth())
    req.add_header("Accept", "application/json")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise JiraError("Jira %s %s: HTTP %d %s" % (method, path, e.code, e.read()[:300].decode("utf-8", "replace")))
    except urllib.error.URLError as e:
        raise JiraError("Jira unreachable: %s" % e.reason)


def adf_to_md(node, depth=0):
    """Atlassian Document Format to Markdown, enough for issue descriptions."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    t = node.get("type")
    kids = node.get("content") or []
    inner = lambda sep="": sep.join(adf_to_md(k, depth) for k in kids)  # noqa: E731
    if t == "text":
        s = node.get("text", "")
        for m in node.get("marks") or []:
            if m["type"] == "code":
                s = "`%s`" % s
            elif m["type"] == "strong":
                s = "**%s**" % s
            elif m["type"] == "link":
                s = "[%s](%s)" % (s, m.get("attrs", {}).get("href", ""))
        return s
    if t == "hardBreak":
        return "\n"
    if t == "paragraph":
        return inner() + "\n\n"
    if t == "heading":
        return "#" * (int(node.get("attrs", {}).get("level", 2)) + 2) + " " + inner() + "\n\n"
    if t in ("bulletList", "orderedList"):
        out = []
        for i, item in enumerate(kids, 1):
            mark = "%d." % i if t == "orderedList" else "-"
            body = "".join(adf_to_md(k, depth + 1) for k in item.get("content") or []).strip()
            out.append("  " * depth + mark + " " + body.replace("\n\n", "\n"))
        return "\n".join(out) + "\n\n"
    if t == "codeBlock":
        return "```%s\n%s\n```\n\n" % (node.get("attrs", {}).get("language", "") or "text", inner())
    if t == "blockquote":
        return "".join("> " + l + "\n" for l in inner().strip().splitlines()) + "\n"
    if t == "table":
        rows = []
        for r in kids:
            rows.append("| " + " | ".join(adf_to_md(c).strip().replace("\n", " ") for c in r.get("content") or []) + " |")
        if rows:
            rows.insert(1, "|" + "---|" * rows[0].count(" | ") + "---|")
        return "\n".join(rows) + "\n\n"
    if t == "mention":
        return "@" + node.get("attrs", {}).get("text", "").lstrip("@")
    if t in ("inlineCard", "blockCard"):
        return node.get("attrs", {}).get("url", "")
    return inner()


def fetch(cfg, key):
    return request(cfg, "GET", "/rest/api/3/issue/%s?fields=%s" % (key, FIELDS))


def to_markdown(cfg, issue):
    f = issue["fields"]
    key = issue["key"]
    desc = adf_to_md(f.get("description")).strip() if isinstance(f.get("description"), dict) else (f.get("description") or "").strip()
    links = []
    for l in f.get("issuelinks") or []:
        other = l.get("outwardIssue") or l.get("inwardIssue") or {}
        rel = l["type"]["outward"] if "outwardIssue" in l else l["type"]["inward"]
        if other:
            links.append("- %s %s: %s" % (rel, other.get("key"), (other.get("fields") or {}).get("summary", "")))
    parent = (f.get("parent") or {}).get("key")
    lines = [
        "# %s · %s" % (key, f.get("summary", "")),
        "",
        "Key: %s" % key,
        "Type: %s" % (f.get("issuetype") or {}).get("name", ""),
        "Status: %s" % (f.get("status") or {}).get("name", ""),
        "Priority: %s" % (f.get("priority") or {}).get("name", ""),
        "Labels: %s" % ", ".join(f.get("labels") or []),
        "Components: %s" % ", ".join(c["name"] for c in f.get("components") or []),
        "Parent: %s" % (parent or ""),
        "Link: %s/browse/%s" % (_base(cfg), key),
        "",
        "## Summary",
        "",
        f.get("summary", ""),
        "",
        "## Description (from Jira)",
        "",
        desc or "_empty in Jira_",
        "",
        "## Acceptance criteria",
        "",
        "<!-- Taken from the description if it has them; otherwise the orchestrator fills this with the engineer. -->",
        "",
        "## Linked issues",
        "",
        "\n".join(links) or "none",
        "",
    ]
    return "\n".join(lines)


def comment(cfg, key, text):
    body = {"body": {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": para}]} for para in text.split("\n\n") if para.strip()
    ]}}
    return request(cfg, "POST", "/rest/api/3/issue/%s/comment" % key, body)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jira.py")
    ap.add_argument("--config", default=".sdlc/config.yml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fetch")
    p.add_argument("key")
    p.add_argument("--write", action="store_true")
    p = sub.add_parser("comment")
    p.add_argument("key")
    p.add_argument("--file", required=True)
    sub.add_parser("check")
    a = ap.parse_args(argv)
    cfg = config.load(a.config) if os.path.exists(a.config) else None
    try:
        if a.cmd == "check":
            me = request(cfg, "GET", "/rest/api/3/myself")
            print("ok: %s (%s)" % (me.get("displayName"), _base(cfg)))
        elif a.cmd == "fetch":
            md = to_markdown(cfg, fetch(cfg, a.key))
            if a.write:
                if cfg is None:
                    raise JiraError(".sdlc/config.yml not found: run /sdlc:init")
                path = os.path.join(config.run_dir(cfg, a.key), "01-task.md")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(md)
                print(path)
            else:
                print(md)
        elif a.cmd == "comment":
            with open(a.file, encoding="utf-8") as f:
                comment(cfg, a.key, f.read())
            print("comment added to %s" % a.key)
    except JiraError as e:
        print("jira: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
