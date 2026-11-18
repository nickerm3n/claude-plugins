import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

GATES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GATES)

CONFIG = """
version: 1
project:
  name: demo
  base_branch: main
tracker:
  type: jira
  base_url: https://example.atlassian.net
pipelines:
  feature: [task, enrich, research, design, qa-plan, plan, code, qa-check, deploy, qa]
  short: [task, research, plan]
commands:
  test: "{test}"
  lint: "{lint}"
  deploy: none
  e2e: "echo e2e ok"
gates:
  max_retries: 2
  forbidden_in_diff: ["\\\\.only\\\\("]
  skipped_tests_regex: "(\\\\d+) skipped"
human:
  design_approval: state
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(text).lstrip("\n"))


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class ProjectCase(unittest.TestCase):
    test_cmd = "echo '10 passed'"
    lint_cmd = "true"

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sdlc-test-")
        self.addCleanup(shutil.rmtree, self.root)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        write(os.path.join(self.root, "src", "app.py"), "def f():\n    return 1\n")
        write(os.path.join(self.root, ".sdlc", "config.yml"), CONFIG.format(test=self.test_cmd, lint=self.lint_cmd))
        git(self.root, "add", ".")
        git(self.root, "commit", "-q", "-m", "init")
        git(self.root, "checkout", "-q", "-b", "feature/PROJ-1-demo")
        import config

        self.cfg = config.load(os.path.join(self.root, ".sdlc", "config.yml"))

    def artifact(self, name, text):
        write(os.path.join(self.root, ".sdlc", "runs", "PROJ-1", name), text)
