import io
import json
import os
import unittest
from unittest import mock

from helpers import ProjectCase, git, write
import run_gate
import state
from checks import phases, repo

PR = ({"url": "https://github.com/o/r/pull/1", "number": 1, "isDraft": True, "state": "OPEN", "labels": ["design-approved"]}, None)


def at_code(case):
    run = state.init(case.cfg, "PROJ-1", "feature", False, "feature/PROJ-1-demo")
    for p in ["task", "enrich", "research", "design", "qa-plan", "plan"]:
        state.advance(case.cfg, run, p)
    return run


class CodeGateTest(ProjectCase):
    def commit(self, path, text):
        write(os.path.join(self.root, path), text)
        git(self.root, "add", ".")
        git(self.root, "commit", "-q", "-m", "c")

    @mock.patch.object(repo, "pr", return_value=PR)
    def test_passes_with_code_change_and_green_commands(self, _):
        run = at_code(self)
        self.commit("src/app.py", "def f():\n    return 2\n")
        self.assertEqual(phases.check_code(self.cfg, "PROJ-1", run), [])

    @mock.patch.object(repo, "pr", return_value=(None, "no pull requests found"))
    def test_only_artifacts_changed_and_no_pr(self, _):
        run = at_code(self)
        self.commit(".sdlc/runs/PROJ-1/06-plan.md", "x\n")
        errors = phases.check_code(self.cfg, "PROJ-1", run)
        self.assertTrue(any("no pull request" in e for e in errors))
        self.assertTrue(any("no code changes outside .sdlc/runs/" in e for e in errors))

    @mock.patch.object(repo, "pr", return_value=PR)
    def test_forbidden_pattern(self, _):
        run = at_code(self)
        self.commit("src/app.test.js", "it.only('x', () => {})\n")
        errors = phases.check_code(self.cfg, "PROJ-1", run)
        self.assertEqual(len(errors), 1)
        self.assertIn("forbidden pattern", errors[0])


class FailingTestsCase(ProjectCase):
    test_cmd = "echo '3 passed, 21 skipped'"

    @mock.patch.object(repo, "pr", return_value=PR)
    def test_skipped_tests_fail_the_gate(self, _):
        run = at_code(self)
        write(os.path.join(self.root, "src/app.py"), "x = 1\n")
        git(self.root, "commit", "-qam", "c")
        errors = phases.check_code(self.cfg, "PROJ-1", run)
        self.assertEqual(errors, ["`echo '3 passed, 21 skipped'` reports 21 skipped test(s), the base branch has 0: un-skip the new ones or ask the engineer"])
        self.cfg["gates"]["skipped_tests_baseline"] = 21
        self.assertEqual(phases.check_code(self.cfg, "PROJ-1", run), [])


class RedTestsCase(ProjectCase):
    test_cmd = "echo boom; exit 1"
    lint_cmd = ""

    @mock.patch.object(repo, "pr", return_value=PR)
    def test_red_tests_and_missing_lint(self, _):
        run = at_code(self)
        write(os.path.join(self.root, "src/app.py"), "x = 1\n")
        git(self.root, "commit", "-qam", "c")
        errors = phases.check_code(self.cfg, "PROJ-1", run)
        self.assertTrue(errors[0].startswith("commands.lint is not set"))
        self.assertIn("failed (exit 1)", errors[1])
        self.assertIn("boom", errors[1])


class HookTest(ProjectCase):
    def hook(self, agent):
        payload = json.dumps({"agent_type": agent, "cwd": self.root, "stop_hook_active": False})
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.root}), mock.patch("sys.stdout", out):
            run_gate.hook(payload)
        return out.getvalue().strip()

    def test_blocks_until_pass_then_escalates(self):
        run = state.init(self.cfg, "PROJ-1", "feature", False, None)
        state.advance(self.cfg, run, "task")
        state.advance(self.cfg, run, "enrich")
        first = json.loads(self.hook("sdlc:researcher"))
        self.assertEqual(first["decision"], "block")
        self.assertIn("retry 1/2", first["reason"])
        self.assertIn("block", self.hook("sdlc:researcher"))
        self.assertEqual(self.hook("sdlc:researcher"), "")
        self.assertEqual(state.load(self.cfg, "PROJ-1")["status"], "escalated")

    def test_ignores_other_agents_and_other_phases(self):
        state.init(self.cfg, "PROJ-1", "feature", False, None)
        self.assertEqual(self.hook("Explore"), "")
        self.assertEqual(self.hook("sdlc:designer"), "")

    def test_judge_report_must_have_verdict(self):
        run = at_code(self)
        state.load(self.cfg, "PROJ-1")
        self.artifact("judge-code-step-1.md", "## Findings\nnone\n")
        self.assertIn("Verdict", self.hook("sdlc:judge-architecture"))
        self.artifact("judge-code-step-1.md", "Verdict: DESIGN_ISSUE\n## Findings\n- Payment state lives in UI, design says domain\n")
        self.assertEqual(self.hook("sdlc:judge-architecture"), "")
        self.assertEqual(phases.check_judge(run_gate.judge_report_path(self.cfg, run, "code"))[0], "DESIGN_ISSUE")


class CommandPhaseTest(ProjectCase):
    def test_deploy_none_and_qa_runs_e2e(self):
        state.init(self.cfg, "PROJ-1", "feature", False, None)
        errors, note = run_gate.gate(self.cfg, "PROJ-1", "deploy")
        self.assertEqual(errors, [])
        self.assertIn("skipped", note)
        errors, note = run_gate.gate(self.cfg, "PROJ-1", "qa")
        self.assertEqual((errors, note), ([], "PASS"))
        self.assertIn("e2e ok", open(os.path.join(self.root, ".sdlc/runs/PROJ-1/10-qa.md")).read())

    def test_deploy_waits_for_merge_then_passes_merge_sha(self):
        run = state.init(self.cfg, "PROJ-1", "feature", False, "feature/PROJ-1-demo")
        run["pr"] = "https://github.com/o/r/pull/1"
        self.cfg["human"]["merge_before_deploy"] = True
        self.cfg["commands"]["deploy"] = 'echo "deploying $SDLC_MERGE_SHA for $SDLC_KEY"'
        with mock.patch.object(repo, "pr", return_value=(dict(PR[0], state="OPEN", mergeCommit=None), None)) as pr:
            errors, _ = run_gate.gate(self.cfg, "PROJ-1", "deploy", run)
            self.assertIn("waiting for the engineer", errors[0])
            pr.assert_called_with(self.root, "https://github.com/o/r/pull/1")
        with mock.patch.object(repo, "pr", return_value=(dict(PR[0], state="MERGED", mergeCommit="abc123"), None)):
            errors, note = run_gate.gate(self.cfg, "PROJ-1", "deploy", run)
        self.assertEqual((errors, note), ([], "PASS"))
        self.assertIn("deploying abc123 for PROJ-1", open(os.path.join(self.root, ".sdlc/runs/PROJ-1/09-deploy.md")).read())

    def test_approval_from_state(self):
        run = state.init(self.cfg, "PROJ-1", "feature", False, None)
        self.assertTrue(phases.check_approval(self.cfg, "PROJ-1", run, "design"))
        state.approve(self.cfg, run, "design", "team")
        self.assertEqual(phases.check_approval(self.cfg, "PROJ-1", run, "design"), [])

    @mock.patch.object(repo, "pr", return_value=({"url": "u", "labels": []}, None))
    def test_approval_from_label(self, _):
        run = state.init(self.cfg, "PROJ-1", "feature", False, None)
        self.cfg["human"]["design_approval"] = "github-label:design-approved"
        self.assertIn("waiting for the team", phases.check_approval(self.cfg, "PROJ-1", run, "design")[0])


if __name__ == "__main__":
    unittest.main()
