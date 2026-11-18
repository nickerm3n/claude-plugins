"""Reads .sdlc/*.yml. Uses PyYAML when it is installed, otherwise a stdlib parser for the subset the templates use:
nested maps by indentation, `- item` lists (also of maps), inline `[a, b]` and `{a: b}`, quoted strings, null/true/false/numbers, `#` comments.
"""

import re

try:
    import yaml as _pyyaml  # type: ignore
except ImportError:
    _pyyaml = None


ESCAPES = {"\\": "\\", '"': '"', "n": "\n", "t": "\t", "/": "/"}


class YamlError(ValueError):
    pass


def load(text):
    if _pyyaml is not None:
        return _pyyaml.safe_load(text)
    return _parse(text)


def load_file(path):
    with open(path, encoding="utf-8") as f:
        return load(f.read())


def _strip_comment(line):
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _split_top(s, sep=","):
    parts, depth, quote, cur = [], 0, None, []
    for ch in s:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


def _split_key(s):
    m = re.match(r"""^("[^"]*"|'[^']*'|[^:]+?):(\s+|$)(.*)$""", s)
    if not m:
        return None
    key = m.group(1).strip()
    if key[:1] in ("'", '"'):
        key = key[1:-1]
    return key, m.group(3).strip()


def _scalar(s):
    s = s.strip()
    if s == "" or s in ("~", "null", "Null", "NULL"):
        return None
    if s[0] == "[" and s[-1] == "]":
        return [_scalar(p) for p in _split_top(s[1:-1])]
    if s[0] == "{" and s[-1] == "}":
        out = {}
        for p in _split_top(s[1:-1]):
            kv = _split_key(p)
            if kv is None:
                raise YamlError("bad inline map item: %r" % p)
            out[kv[0]] = _scalar(kv[1])
        return out
    if s[0] == "'" and s[-1] == "'" and len(s) >= 2:
        return s[1:-1].replace("''", "'")
    if s[0] == '"' and s[-1] == '"' and len(s) >= 2:
        return re.sub(r'\\(.)', lambda m: ESCAPES.get(m.group(1), "\\" + m.group(1)), s[1:-1])
    if s in ("true", "True", "yes"):
        return True
    if s in ("false", "False", "no"):
        return False
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d*", s):
        return float(s)
    return s


def _parse(text):
    lines = []
    for raw in text.splitlines():
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlError("tabs are not allowed for indentation")
        line = _strip_comment(raw)
        if line.strip() == "" or line.strip() == "---":
            continue
        lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    if not lines:
        return None
    value, pos = _block(lines, 0, lines[0][0])
    if pos != len(lines):
        raise YamlError("unexpected indentation near: %r" % lines[pos][1])
    return value


def _block(lines, pos, indent):
    if lines[pos][1].startswith("- ") or lines[pos][1] == "-":
        return _list(lines, pos, indent)
    return _map(lines, pos, indent)


def _map(lines, pos, indent):
    out = {}
    while pos < len(lines) and lines[pos][0] == indent and not lines[pos][1].startswith("-"):
        kv = _split_key(lines[pos][1])
        if kv is None:
            raise YamlError("expected `key: value`, got %r" % lines[pos][1])
        key, rest = kv
        pos += 1
        if rest:
            out[key] = _scalar(rest)
        elif pos < len(lines) and (lines[pos][0] > indent or (lines[pos][0] == indent and lines[pos][1].startswith("-"))):
            out[key], pos = _block(lines, pos, lines[pos][0])
        else:
            out[key] = None
    return out, pos


def _list(lines, pos, indent):
    out = []
    while pos < len(lines) and lines[pos][0] == indent and (lines[pos][1].startswith("- ") or lines[pos][1] == "-"):
        item = lines[pos][1][1:].strip()
        if item == "":
            pos += 1
            value, pos = _block(lines, pos, lines[pos][0])
            out.append(value)
            continue
        kv = _split_key(item) if item[0] not in "[{'\"" else None
        if kv is None:
            out.append(_scalar(item))
            pos += 1
            continue
        child_indent = indent + 2
        lines[pos] = (child_indent, item)
        value, pos = _map(lines, pos, child_indent)
        out.append(value)
    return out, pos
