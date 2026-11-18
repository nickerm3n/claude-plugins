"""Used by /sdlc:init: guess the stack from marker files and print suggested commands as YAML for the engineer to confirm.
The presets are suggestions, never defaults the gate trusts: init writes them only after the engineer confirmed each one.

  detect_stack.py [--root .]
"""

import argparse
import json
import os
import sys

PRESETS = {
    "node-ts": {
        "test": "npm test",
        "lint": "npm run lint",
        "coverage": "npx jest --coverage --coverageReporters=lcov",
        "complexity": "lizard -l javascript -l typescript --csv src > .sdlc/reports/lizard.csv",
        "mutation": "npx stryker run --reporters json",
        "sast": "semgrep scan --config auto --error",
        "reports": {"coverage": "coverage/lcov.info", "complexity": ".sdlc/reports/lizard.csv", "mutation": "reports/mutation/mutation.json"},
        "forbidden_in_diff": ["\\b(it|describe|test)\\.only\\(", "\\b(it|describe|test)\\.skip\\(", "\\bxit\\("],
        "skipped_tests_regex": "(\\d+) skipped",
    },
    "python": {
        "test": "pytest -q",
        "lint": "ruff check .",
        "coverage": "pytest --cov --cov-report=xml",
        "complexity": "lizard -l python --csv . > .sdlc/reports/lizard.csv",
        "mutation": "mutmut run",
        "sast": "semgrep scan --config auto --error",
        "reports": {"coverage": "coverage.xml", "complexity": ".sdlc/reports/lizard.csv", "mutation": None},
        "forbidden_in_diff": ["@pytest\\.mark\\.skip", "@unittest\\.skip"],
        "skipped_tests_regex": "(\\d+) skipped",
    },
    "go": {
        "test": "go test ./...",
        "lint": "golangci-lint run",
        "coverage": "go test -coverprofile=cover.out ./... && gcov2lcov -infile cover.out -outfile cover.lcov",
        "complexity": "lizard -l go --csv . > .sdlc/reports/lizard.csv",
        "mutation": "go-mutesting ./...",
        "sast": "semgrep scan --config auto --error",
        "reports": {"coverage": "cover.lcov", "complexity": ".sdlc/reports/lizard.csv", "mutation": None},
        "forbidden_in_diff": ["t\\.Skip\\("],
        "skipped_tests_regex": None,
    },
    "java": {
        "test": "./gradlew test",
        "lint": "./gradlew check -x test",
        "coverage": "./gradlew jacocoTestReport",
        "complexity": "lizard -l java --csv src > .sdlc/reports/lizard.csv",
        "mutation": "./gradlew pitest",
        "sast": "semgrep scan --config auto --error",
        "reports": {"coverage": "build/reports/jacoco/test/jacocoTestReport.xml", "complexity": ".sdlc/reports/lizard.csv", "mutation": None},
        "forbidden_in_diff": ["@Disabled", "@Ignore"],
        "skipped_tests_regex": None,
    },
}

MARKERS = [
    ("node-ts", ["package.json", "tsconfig.json"]),
    ("python", ["pyproject.toml", "setup.py", "requirements.txt"]),
    ("go", ["go.mod"]),
    ("java", ["build.gradle", "build.gradle.kts", "pom.xml"]),
]


def detect(root):
    found = []
    for stack, files in MARKERS:
        hits = [f for f in files if os.path.exists(os.path.join(root, f))]
        if hits:
            found.append((stack, hits))
    return found


def node_scripts(root):
    p = os.path.join(root, "package.json")
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return (json.load(f).get("scripts") or {})
    except ValueError:
        return {}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="detect_stack.py")
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    found = detect(a.root)
    if not found:
        print("stack: custom   # no marker file found; ask the engineer for every command")
        return 0
    for stack, hits in found:
        print("# detected %s from %s" % (stack, ", ".join(hits)))
    stack = found[0][0]
    preset = PRESETS[stack]
    print("stack: %s" % stack)
    if stack == "node-ts":
        scripts = node_scripts(a.root)
        print("# package.json scripts: %s" % (", ".join(sorted(scripts)) or "none"))
    print("suggested_commands:")
    for k in ("test", "lint", "coverage", "complexity", "mutation", "sast"):
        print("  %s: %s" % (k, json.dumps(preset[k])))
    print("suggested_reports: %s" % json.dumps(preset["reports"]))
    print("suggested_forbidden_in_diff: %s" % json.dumps(preset["forbidden_in_diff"]))
    print("suggested_skipped_tests_regex: %s" % json.dumps(preset["skipped_tests_regex"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
