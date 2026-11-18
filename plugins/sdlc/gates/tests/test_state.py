import json
import os
import shutil
import subprocess
import unittest

from helpers import GATES, ProjectCase
import state


class StateTest(ProjectCase):
    def test_happy_path_and_board(self):
        run = state.init(self.cfg, "PROJ-1", "short", False, "feature/PROJ-1-demo")
        self.assertEqual(run["current"], "task")
        self.assertEqual(state.advance(self.cfg, run, "task"), "research")
        self.assertEqual(state.advance(self.cfg, run, "research"), "plan")
        self.assertIsNone(state.advance(self.cfg, run, "plan"))
        self.assertEqual(run["status"], "done")
        saved = json.load(open(os.path.join(self.root, ".sdlc/runs/PROJ-1/run.json")))
        self.assertEqual(saved["phase_status"], {"task": "passed", "research": "passed", "plan": "passed"})
        board = open(os.path.join(self.root, ".sdlc/runs/index.html")).read()
        self.assertIn("PROJ-1", board)
        self.assertNotIn('http-equiv="refresh"', board)

    def test_wrong_phase_refused(self):
        run = state.init(self.cfg, "PROJ-1", "feature", False, None)
        with self.assertRaises(SystemExit):
            state.advance(self.cfg, run, "design")

    def test_retries_then_escalation_then_human(self):
        run = state.init(self.cfg, "PROJ-1", "feature", False, None)
        self.assertTrue(state.fail(self.cfg, run, "task", "x"))
        self.assertTrue(state.fail(self.cfg, run, "task", "x"))
        self.assertFalse(state.fail(self.cfg, run, "task", "x"))
        self.assertEqual(run["status"], "escalated")
        with self.assertRaises(SystemExit):
            state.start(self.cfg, run, "task")
        state.approve(self.cfg, run, "task", "mykyta")
        self.assertEqual(run["status"], "running")
        self.assertEqual(run["retries"]["task"], 0)

    def test_rewind_from_code_to_design(self):
        run = state.init(self.cfg, "PROJ-1", "feature", False, None)
        for p in ["task", "enrich", "research", "design", "qa-plan", "plan"]:
            state.advance(self.cfg, run, p)
        run["approvals"]["design"] = {"by": "x", "at": "t"}
        self.assertEqual(run["current"], "code")
        state.rewind(self.cfg, run, "design", "mykyta", "judge found a design error")
        self.assertEqual(run["current"], "design")
        self.assertNotIn("design", run["approvals"])
        self.assertEqual(run["phase_status"]["code"], "pending")
        with self.assertRaises(SystemExit):
            state.rewind(self.cfg, run, "qa", "mykyta", "forward")

    def test_dry_run_skips_code_phases(self):
        run = state.init(self.cfg, "PROJ-1", "feature", True, None)
        for p in ["task", "enrich", "research", "design", "qa-plan"]:
            state.advance(self.cfg, run, p)
        self.assertIsNone(state.advance(self.cfg, run, "plan"))
        self.assertEqual(run["phase_status"]["code"], "skipped")
        self.assertEqual(run["status"], "done")

    def test_current_key_from_branch(self):
        state.init(self.cfg, "PROJ-1", "feature", False, None)
        self.assertEqual(state.current_key(self.cfg), "PROJ-1")

    def test_init_validates(self):
        with self.assertRaises(SystemExit):
            state.init(self.cfg, "not-a-key", "feature", False, None)
        with self.assertRaises(SystemExit):
            state.init(self.cfg, "PROJ-2", "bugfix", False, None)

    def test_summary(self):
        run = state.init(self.cfg, "PROJ-1", "feature", False, None)
        state.advance(self.cfg, run, "task")
        state.wait(self.cfg, run, "enrich", "interview")
        self.assertEqual(state.summary(run), "PROJ-1 ▸ enrich 2/10 ⏸ waiting for human")

    def test_gate_steps_for_the_pane(self):
        self.cfg["judges"] = {"research": True, "code": True}
        self.cfg["human"]["merge_before_deploy"] = True
        run = state.init(self.cfg, "PROJ-1", "feature", False, None)
        plan = run["gate_plan"]
        self.assertEqual(plan["task"], ["code"])
        self.assertEqual(plan["enrich"], ["code", "human"])
        self.assertEqual(plan["research"], ["code", "judge"])
        self.assertEqual(plan["code"], ["code", "judge"])
        self.assertEqual(plan["deploy"], ["code", "human"])
        state.record(self.cfg, run, "task", "code", "fail", "2 violation(s)")
        state.record(self.cfg, run, "task", "judge", "PASS")
        self.assertEqual(run["gates"]["task"], {"code": {"status": "fail", "at": run["gates"]["task"]["code"]["at"], "detail": "2 violation(s)"}})
        state.record(self.cfg, run, "task", "code", "pass")
        state.advance(self.cfg, run, "task")
        state.wait(self.cfg, run, "enrich", "interview")
        self.assertEqual(run["gates"]["enrich"]["human"]["status"], "waiting")
        state.advance(self.cfg, run, "enrich", "engineer confirmed")
        self.assertEqual(run["gates"]["enrich"]["human"]["status"], "approved")
        state.rewind(self.cfg, run, "task", "mykyta", "again")
        self.assertEqual(run["gates"]["enrich"], {"code": {"status": "pending"}, "human": {"status": "pending"}})

    @unittest.skipIf(shutil.which("jq") is None, "jq not installed")
    def test_statusline_script(self):
        run = state.init(self.cfg, "PROJ-1", "feature", False, None)
        for p in ["task", "enrich", "research", "design", "qa-plan", "plan"]:
            state.advance(self.cfg, run, p)
        run["plan_step"] = 2
        state.fail(self.cfg, run, "code", "red")
        script = os.path.join(os.path.dirname(GATES), "templates", "statusline.sh")
        out = subprocess.run(["bash", script], input=json.dumps({"workspace": {"project_dir": self.root}}),
                             capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out, "sdlc PROJ-1 ▸ code 7/10 step 2 ↻1")


if __name__ == "__main__":
    unittest.main()
