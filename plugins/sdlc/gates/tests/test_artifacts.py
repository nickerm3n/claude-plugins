import unittest

from helpers import ProjectCase
import state
from checks import mermaid, phases

C4 = """```mermaid
C4Context
  Person(user, "User")
  System(app, "App")
  Rel(user, app, "uses")
```"""
SEQ = """```mermaid
sequenceDiagram
  User->>App: request
  App-->>User: response
```"""
DFD = """```mermaid
flowchart LR
  A[Form] --> B[(DB)]
```"""

DESIGN = """# Design
## Context
Checkout gets a promo code field.
{c4}
## Containers and components
The API validates codes.
## Sequence
{seq}
## Data flow
{dfd}
## Decisions
- validate server side
## Risks
- none known
"""


class ArtifactGateTest(ProjectCase):
    def setUp(self):
        super().setUp()
        state.init(self.cfg, "PROJ-1", "feature", False, "feature/PROJ-1-demo")

    def gate(self, phase):
        return phases.check_artifact(self.cfg, "PROJ-1", phase)

    def test_missing_artifact(self):
        self.assertIn("does not exist", self.gate("research")[0])

    def test_task_needs_key_and_sections(self):
        self.artifact("01-task.md", "# x\n## Summary\nDo it\n## Acceptance criteria\n- works\n")
        self.assertEqual(self.gate("task"), ["missing line `Key: PROJ-1` (the Jira issue this run is for)"])
        self.artifact("01-task.md", "# x\nKey: PROJ-1\n## Summary\nDo it\n## Acceptance criteria\n<!-- fill -->\n")
        self.assertIn("section `## Acceptance criteria` is empty", self.gate("task"))

    def test_research_refs_must_exist(self):
        self.artifact("03-research.md", """
## Scope
promo codes
## Relevant code
- `src/app.py:1` entry
- `src/missing.py` gone
- `src/app.py:99` too far
## Knowledge base
none
## Constraints
## Risks
- money
""")
        errors = self.gate("research")
        self.assertIn("referenced path does not exist: `src/missing.py`", errors)
        self.assertTrue(any("points past the end" in e for e in errors))
        self.assertEqual(len(errors), 2)

    def test_design_needs_three_parsing_diagrams(self):
        self.artifact("04-design.md", DESIGN.format(c4=C4, seq=SEQ, dfd=DFD))
        self.assertEqual(self.gate("design"), [])
        self.artifact("04-design.md", DESIGN.format(c4="", seq=SEQ, dfd=DFD))
        self.assertIn("required c4 diagram is missing or does not parse", self.gate("design"))
        broken = "```mermaid\nsequenceDiagram\n  participant A\n```"
        self.artifact("04-design.md", DESIGN.format(c4=C4, seq=broken, dfd=DFD))
        errors = self.gate("design")
        self.assertTrue(any("no message arrow" in e for e in errors), errors)

    def test_plan_phases_have_goal_and_done_and_no_code(self):
        self.artifact("06-plan.md", """
## Phases
### Phase 1: Domain
Goal: model the promo code
Done when: unit tests for PromoCode pass
### Phase 2: API
Goal: endpoint
```python
def x(): pass
```
""")
        errors = self.gate("plan")
        self.assertIn("`Phase 2: API` has no `Done when:` line", errors)
        self.assertTrue(any("code block `python`" in e for e in errors))
        self.assertEqual(phases.plan_phases(self.cfg, "PROJ-1"), ["Phase 1: Domain", "Phase 2: API"])

    def test_qa_check_covers_every_planned_scenario(self):
        self.artifact("05-qa-plan.md", "## Contracts\nPOST /promo\n## Scenarios\n- QA-1 valid\n- QA-2 expired\n## Tests to add or change\n- api test\n")
        self.assertEqual(self.gate("qa-plan"), [])
        self.artifact("08-qa-check.md", "## Contract changes\nnone\n## Scenario status\n| QA-1 | ok |\n")
        self.assertEqual(self.gate("qa-check"), ["`## Scenario status` does not cover QA-2 from 05-qa-plan.md"])

    def test_artifact_size_limit(self):
        self.cfg["thresholds"]["artifact_max_lines"] = 5
        self.artifact("02-enrich.md", "## Engineer's view\na\n## Decisions\nb\n## Constraints\nc\n## Pitfalls\n## Open questions\n")
        self.assertTrue(any("limit is 5" in e for e in self.gate("enrich")))

    def test_project_can_override_sections(self):
        self.cfg["artifacts"] = {"deploy": {"sections": ["Env"], "non_empty": []}}
        self.artifact("09-deploy.md", "## Env\n")
        self.assertEqual(self.gate("deploy"), [])


class MermaidTest(unittest.TestCase):
    def test_unclosed_and_unknown(self):
        self.assertIn("not closed", mermaid.check("```mermaid\nflowchart LR\nA-->B\n", [])[0])
        self.assertIn("unknown diagram type", mermaid.check("```mermaid\nfoo\nbar\n```", [], use_mmdc=False)[0])

    def test_unbalanced(self):
        errs = mermaid.check("```mermaid\nflowchart LR\nA[x --> B\n```", ["dfd"], use_mmdc=False)
        self.assertTrue(any("unbalanced" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
