"""Structure checks on Markdown artifacts. Each check returns a list of violations (strings); empty means clean."""

import os
import re

PLACEHOLDER = re.compile(r"^\s*(-|\*|tbd|todo|n/?a|none|\.\.\.|<[^>]*>)?\s*$", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)\s*([\w-]*)")


def strip_fences(text):
    out, inside = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            inside = not inside
            out.append("")
            continue
        out.append("" if inside else line)
    return out


def sections(text):
    """Map of lowercased heading -> body text, for headings outside code fences."""
    lines = strip_fences(text)
    raw = text.splitlines()
    heads = []
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip().lower()))
    out = {}
    for n, (i, level, name) in enumerate(heads):
        end = len(raw)
        for j, lvl, _ in heads[n + 1 :]:
            if lvl <= level:
                end = j
                break
        out.setdefault(name, "\n".join(raw[i + 1 : end]))
    return out


def has_content(body):
    for line in strip_fences(body):
        if HEADING.match(line):
            continue
        if not PLACEHOLDER.match(line):
            return True
    return "```" in body


def require_sections(text, names, non_empty=()):
    found = sections(text)
    errors = []
    for name in names:
        key = name.lower()
        if key not in found:
            errors.append("missing section `## %s`" % name)
        elif name in non_empty and not has_content(found[key]):
            errors.append("section `## %s` is empty" % name)
    return errors


def max_lines(text, limit, what="artifact"):
    n = len(text.splitlines())
    if limit and n > limit:
        return ["%s has %d lines, limit is %d: cut it down, keep only what the next phase needs" % (what, n, limit)]
    return []


PATH_TOKEN = re.compile(r"`([^`\s]+?)(?::(\d+)(?:-\d+)?)?`")
LOOKS_LIKE_PATH = re.compile(r"^(\.{0,2}/)?[\w.@-]+(/[\w.@\[\]-]+)*\.[A-Za-z0-9]{1,8}$|^(\.{0,2}/)?[\w.@-]+(/[\w.@\[\]-]+)+/?$")


def file_refs(text):
    refs = []
    for line in strip_fences(text):
        for m in PATH_TOKEN.finditer(line):
            token = m.group(1)
            if "://" in token or "*" in token or token.startswith("-") or not LOOKS_LIKE_PATH.match(token):
                continue
            refs.append((token, int(m.group(2)) if m.group(2) else None))
    return refs


def refs_exist(text, root):
    errors = []
    for path, line in file_refs(text):
        full = os.path.join(root, path)
        if not os.path.exists(full):
            errors.append("referenced path does not exist: `%s`" % path)
        elif line and os.path.isfile(full):
            with open(full, encoding="utf-8", errors="replace") as f:
                count = sum(1 for _ in f)
            if line > count:
                errors.append("`%s:%d` points past the end of the file (%d lines)" % (path, line, count))
    return errors


def code_fences(text, allowed=("mermaid",)):
    errors = []
    for line in text.splitlines():
        m = FENCE.match(line)
        if m and m.group(2) and m.group(2).lower() not in allowed:
            errors.append("code block `%s` is not allowed in this artifact: describe the change, do not write the code" % m.group(2))
    inside = False
    for line in text.splitlines():
        m = FENCE.match(line)
        if m:
            if not inside and not m.group(2):
                errors.append("unlabelled code block is not allowed in this artifact")
            inside = not inside
    return sorted(set(errors))


def ids(text, pattern):
    return sorted(set(re.findall(pattern, text)))
