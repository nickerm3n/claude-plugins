"""Mermaid diagrams in artifacts: presence by kind and a parse check (mmdc when installed, structural otherwise)."""

import os
import re
import shutil
import subprocess
import tempfile

KINDS = {
    "c4": re.compile(r"^C4(Context|Container|Component|Dynamic|Deployment)\b"),
    "sequence": re.compile(r"^sequenceDiagram\b"),
    "dfd": re.compile(r"^(flowchart|graph)\b"),
    "class": re.compile(r"^classDiagram\b"),
    "er": re.compile(r"^erDiagram\b"),
    "state": re.compile(r"^stateDiagram(-v2)?\b"),
}

BODY = {
    "c4": (re.compile(r"\b(Person|System|System_Ext|Container|ContainerDb|Component|Rel|BiRel|Boundary|System_Boundary|Container_Boundary)(_\w+)?\s*\("), "no C4 element (Person/System/Container/Component/Rel)"),
    "sequence": (re.compile(r"(-->>|->>|-->|->|--x|-x|--\)|-\))"), "no message arrow"),
    "dfd": (re.compile(r"(-->|---|-\.->|==>|--\s*[^-]+?\s*-->)"), "no edge"),
}


def blocks(text):
    out, cur, inside, start = [], [], False, 0
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not inside and re.match(r"^(```|~~~)\s*mermaid\s*$", stripped):
            inside, cur, start = True, [], i
            continue
        if inside and re.match(r"^(```|~~~)\s*$", stripped):
            out.append((start, "\n".join(cur)))
            inside = False
            continue
        if inside:
            cur.append(line)
    if inside:
        out.append((start, None))
    return out


def header(body):
    in_front = False
    for line in body.splitlines():
        s = line.strip()
        if s == "---":
            in_front = not in_front
            continue
        if in_front or not s or s.startswith("%%"):
            continue
        return s
    return ""


def kind_of(body):
    h = header(body)
    for kind, rx in KINDS.items():
        if rx.match(h):
            return kind
    return None


def _balanced(body):
    pairs = {")": "(", "]": "[", "}": "{"}
    stack, quote = [], False
    for ch in body:
        if ch == '"':
            quote = not quote
        if quote:
            continue
        if ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack and not quote


def structural_errors(body):
    kind = kind_of(body)
    if kind is None:
        return ["unknown diagram type `%s`" % (header(body) or "<empty>")]
    errors = []
    lines = [l for l in body.splitlines() if l.strip() and not l.strip().startswith("%%")]
    if len(lines) < 2:
        errors.append("%s diagram has no body" % kind)
    if not _balanced(body):
        errors.append("%s diagram has unbalanced brackets or quotes" % kind)
    rule = BODY.get(kind)
    if rule and not rule[0].search(body):
        errors.append("%s diagram: %s" % (kind, rule[1]))
    return errors


def mmdc_errors(body):
    exe = shutil.which("mmdc")
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, "d.mmd"), os.path.join(d, "d.svg")
        with open(src, "w", encoding="utf-8") as f:
            f.write(body)
        try:
            p = subprocess.run([exe, "-q", "-i", src, "-o", out], capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return ["mmdc timed out"]
        if p.returncode != 0:
            msg = (p.stderr or p.stdout).strip().splitlines()
            return ["mmdc: %s" % (msg[0] if msg else "parse failed")]
    return []


def check(text, required_kinds, use_mmdc=True):
    errors, present = [], set()
    for line, body in blocks(text):
        if body is None:
            errors.append("mermaid block at line %d is not closed" % line)
            continue
        problems = structural_errors(body)
        if not problems and use_mmdc:
            problems = mmdc_errors(body) or []
        for p in problems:
            errors.append("mermaid block at line %d: %s" % (line, p))
        if not problems:
            present.add(kind_of(body))
    for kind in required_kinds:
        if kind not in present:
            errors.append("required %s diagram is missing or does not parse" % kind)
    return errors
