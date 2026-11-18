import os
import unittest

from helpers import GATES  # noqa: F401
import yamlish

TEMPLATE = os.path.join(os.path.dirname(GATES), "templates", "config.yml")


class YamlishTest(unittest.TestCase):
    def parse(self, text):
        return yamlish._parse(text)

    def test_nested_maps_lists_and_scalars(self):
        data = self.parse(
            """
version: 1   # comment
project:
  name: "demo # not a comment"
  stack: node-ts
pipelines:
  feature: [task, enrich]
models: {writer: sonnet, judge: opus}
thresholds:
  crap_max: null
  min: 80.5
flags:
  - a
  - b
domains:
  - path: src/billing/**
    type: core
    owners: ["@org/pay"]
  - path: src/ui/**
    type: generic
"""
        )
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["project"]["name"], "demo # not a comment")
        self.assertEqual(data["pipelines"]["feature"], ["task", "enrich"])
        self.assertEqual(data["models"], {"writer": "sonnet", "judge": "opus"})
        self.assertIsNone(data["thresholds"]["crap_max"])
        self.assertEqual(data["thresholds"]["min"], 80.5)
        self.assertEqual(data["flags"], ["a", "b"])
        self.assertEqual(data["domains"][0], {"path": "src/billing/**", "type": "core", "owners": ["@org/pay"]})
        self.assertEqual(data["domains"][1]["type"], "generic")

    def test_regex_strings_survive(self):
        data = self.parse('gates:\n  forbidden_in_diff: ["\\\\b(it|test)\\\\.only\\\\(", "@Disabled"]\n')
        self.assertEqual(len(data["gates"]["forbidden_in_diff"]), 2)
        self.assertEqual(data["gates"]["forbidden_in_diff"][1], "@Disabled")

    def test_tabs_rejected(self):
        with self.assertRaises(yamlish.YamlError):
            self.parse("a:\n\tb: 1\n")

    def test_shipped_templates_parse(self):
        for name in ("config.yml", "domain-map.yml"):
            path = os.path.join(os.path.dirname(GATES), "templates", name)
            with open(path, encoding="utf-8") as f:
                data = yamlish._parse(f.read())
            self.assertIsInstance(data, dict, name)


@unittest.skipIf(yamlish._pyyaml is None, "PyYAML not installed")
class ParityTest(unittest.TestCase):
    def test_same_result_as_pyyaml(self):
        import helpers

        texts = [helpers.CONFIG.format(test="a", lint="b")]
        for name in ("config.yml", "domain-map.yml"):
            with open(os.path.join(os.path.dirname(GATES), "templates", name), encoding="utf-8") as f:
                texts.append(f.read())
        for text in texts:
            self.assertEqual(yamlish._parse(text), yamlish._pyyaml.safe_load(text))


if __name__ == "__main__":
    unittest.main()
