import json
import os
import tempfile
import unittest
from unittest import mock

from helpers import ProjectCase, git, write
import domain
import jira
import state
from checks import phases, quality, repo

LIZARD = """NLOC,CCN,token,PARAM,length,location,file,function,long_name,start,end
10,12,80,1,12,"risky@1-12@src/a.py",src/a.py,risky,risky(x),1,12
3,1,10,0,3,"safe@20-22@src/a.py",src/a.py,safe,safe(),20,22
"""
LCOV = "SF:/ci/work/src/a.py\nDA:1,0\nDA:5,0\nDA:20,3\nDA:21,1\nend_of_record\n"


class CrapTest(unittest.TestCase):
    def test_formula(self):
        self.assertEqual(quality.crap(1, 1.0), 1)
        self.assertEqual(quality.crap(10, 0.0), 110)
        self.assertAlmostEqual(quality.crap(10, 0.5), 22.5)

    def test_rows_from_lizard_and_lcov(self):
        d = tempfile.mkdtemp()
        comp, cov = os.path.join(d, "l.csv"), os.path.join(d, "lcov.info")
        open(comp, "w").write(LIZARD)
        open(cov, "w").write(LCOV)
        rows = quality.crap_rows(quality.read_lizard(comp), quality.read_coverage(cov))
        self.assertEqual(rows[0]["function"], "risky")
        self.assertEqual(rows[0]["crap"], 156)
        self.assertEqual(rows[1]["crap"], 1)

    def test_cobertura(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "c.xml")
        open(p, "w").write('<coverage><packages><package><classes><class filename="src/a.py"><lines>'
                           '<line number="1" hits="1"/><line number="2" hits="0"/></lines></class></classes></package></packages></coverage>')
        self.assertEqual(quality.read_coverage(p), {"src/a.py": {1: 1, 2: 0}})

    def test_mutation_score(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "m.json")
        json.dump({"files": {"a.ts": {"mutants": [{"status": "Killed"}, {"status": "Survived"}, {"status": "Timeout"}, {"status": "Ignored"}]}}}, open(p, "w"))
        score, total = quality.mutation_score(p)
        self.assertEqual(total, 3)
        self.assertAlmostEqual(score, 66.666, places=2)


class CiGateTest(ProjectCase):
    def test_thresholds_from_config(self):
        write(os.path.join(self.root, "r/l.csv"), LIZARD)
        write(os.path.join(self.root, "r/lcov.info"), LCOV)
        self.cfg["reports"] = {"complexity": "r/l.csv", "coverage": "r/lcov.info", "mutation": None}
        self.cfg["thresholds"].update({"crap_max": 30, "complexity_max": 10, "mutation_score_min": 60})
        self.cfg["gates"]["ci_scope"] = "all"
        errors = quality.check(self.cfg)
        self.assertTrue(any("cyclomatic complexity 12 > 10" in e for e in errors))
        self.assertTrue(any("CRAP 156.0 > 30" in e for e in errors))
        self.assertTrue(any("reports.mutation" in e for e in errors))


class ChangedScopeTest(ProjectCase):
    LIZARD = (
        "NLOC,CCN,token,PARAM,length,location,file,function,long_name,start,end\n"
        '10,20,80,1,5,"touched@1-5@src/big.py",src/big.py,touched,touched(),1,5\n'
        '10,22,80,1,11,"untouched@10-20@src/big.py",src/big.py,untouched,untouched(),10,20\n'
        '10,30,80,1,9,"elsewhere@1-9@src/old.py",src/old.py,elsewhere,elsewhere(),1,9\n'
    )

    def setUp(self):
        super().setUp()
        write(os.path.join(self.root, "src/big.py"), "".join("line %d\n" % i for i in range(1, 31)))
        git(self.root, "add", ".")
        git(self.root, "commit", "-q", "-m", "big file")
        git(self.root, "branch", "base-a")
        write(os.path.join(self.root, "src/big.py"), "".join(("changed 2\n" if i == 2 else "line %d\n" % i) for i in range(1, 31)))
        git(self.root, "commit", "-qam", "touch line 2")
        write(os.path.join(self.root, "r/l.csv"), self.LIZARD)
        self.cfg["project"]["base_branch"] = "base-a"
        self.cfg["reports"] = {"complexity": "r/l.csv", "coverage": None, "mutation": None}
        self.cfg["thresholds"]["complexity_max"] = 15

    def test_only_functions_the_branch_touched_are_checked(self):
        errors = quality.check(self.cfg)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("src/big.py:1 touched cyclomatic complexity 20 > 15", errors[0])

    def test_scope_all_checks_the_whole_report(self):
        self.cfg["gates"]["ci_scope"] = "all"
        self.assertEqual(len(quality.check(self.cfg)), 3)

    def test_ranges_follow_the_diff(self):
        self.assertEqual(quality.changed_ranges(self.root, "base-a"), {"src/big.py": [(2, 2)]})

    def test_unknown_base_is_reported_not_ignored(self):
        self.cfg["project"]["base_branch"] = "nope"
        errors = quality.check(self.cfg)
        self.assertTrue(any("cannot compute the diff" in e for e in errors), errors)

    def test_command_none_is_skipped_not_executed(self):
        self.cfg["commands"]["dast"] = "none"
        with mock.patch.object(repo, "run_command", return_value=(0, "")) as run:
            quality.check(self.cfg)
        self.assertNotIn("none", [c.args[0] for c in run.call_args_list])

    def test_mutation_can_be_skipped_on_purpose(self):
        self.cfg["thresholds"]["mutation_score_min"] = 60
        self.assertTrue(any("reports.mutation" in e for e in quality.check(self.cfg)))
        self.assertFalse(any("mutation" in e for e in quality.check(self.cfg, ["mutation"])))

    def test_code_gate_passes_ci_skip_to_the_quality_checks(self):
        run = state.init(self.cfg, "PROJ-1", "feature", False, "feature/PROJ-1-demo")
        self.cfg["gates"]["local_ci"] = True
        self.cfg["thresholds"]["complexity_max"] = None
        self.cfg["thresholds"]["mutation_score_min"] = 60
        pr = ({"url": "u", "state": "OPEN", "labels": []}, None)
        with mock.patch.object(repo, "pr", return_value=pr):
            self.assertTrue(any("reports.mutation" in e for e in phases.check_code(self.cfg, "PROJ-1", run)))
            self.cfg["gates"]["ci_skip"] = ["mutation"]
            self.assertFalse(any("mutation" in e for e in phases.check_code(self.cfg, "PROJ-1", run)))


class DomainTest(unittest.TestCase):
    DOMAINS = [
        {"path": "src/**", "type": "supporting"},
        {"path": ["src/billing/**", "src/checkout/*.ts"], "type": "core", "name": "payments", "owners": ["@o/pay"]},
        {"path": "src/ui/**", "type": "generic"},
    ]

    def test_last_match_wins(self):
        self.assertEqual(domain.classify("src/billing/x/y.ts", "supporting", self.DOMAINS), ("core", "payments"))
        self.assertEqual(domain.classify("src/checkout/a.ts", "supporting", self.DOMAINS)[0], "core")
        self.assertEqual(domain.classify("src/checkout/deep/a.ts", "supporting", self.DOMAINS)[0], "supporting")
        self.assertEqual(domain.classify("src/ui/b.tsx", "supporting", self.DOMAINS)[0], "generic")
        self.assertEqual(domain.classify("README.md", "supporting", self.DOMAINS), ("supporting", None))

    def test_codeowners(self):
        out = domain.codeowners(self.DOMAINS)
        self.assertIn("/src/billing/** @o/pay  # core · payments", out)
        self.assertNotIn("src/ui", out)


class JiraAdfTest(unittest.TestCase):
    def test_adf_to_markdown(self):
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Add "}, {"type": "text", "text": "promo", "marks": [{"type": "code"}]}]},
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "AC"}]},
            {"type": "bulletList", "content": [{"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "valid code"}]}]}]},
        ]}
        md = jira.adf_to_md(doc)
        self.assertIn("Add `promo`", md)
        self.assertIn("#### AC", md)
        self.assertIn("- valid code", md)

    def test_task_markdown_passes_key_check(self):
        issue = {"key": "PROJ-1", "fields": {"summary": "Promo", "description": None, "issuetype": {"name": "Story"}}}
        md = jira.to_markdown({"tracker": {"base_url": "https://x.atlassian.net"}}, issue)
        self.assertIn("\nKey: PROJ-1\n", md)
        self.assertIn("https://x.atlassian.net/browse/PROJ-1", md)


if __name__ == "__main__":
    unittest.main()
