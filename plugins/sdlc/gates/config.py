"""Project config (.sdlc/config.yml) with defaults. The plugin knows nothing about the stack: commands come from here."""

import copy
import os

import yamlish

DEFAULT_PIPELINE = ["task", "enrich", "research", "design", "qa-plan", "plan", "code", "qa-check", "deploy", "qa"]

DEFAULTS = {
    "version": 1,
    "project": {"name": None, "stack": "custom", "base_branch": "main", "artifact_language": "en"},
    "tracker": {"type": "jira", "base_url": None, "project_key": None},
    "pipelines": {"feature": DEFAULT_PIPELINE},
    "models": {"writer": "sonnet", "judge": "opus"},
    "commands": {},
    "reports": {"coverage": None, "complexity": None},
    "thresholds": {
        "crap_max": None,
        "mutation_score_min": None,
        "complexity_max": None,
        "plan_max_lines": 300,
        "artifact_max_lines": 600,
    },
    "gates": {
        "max_retries": 3,
        "forbidden_in_diff": [],
        "skipped_tests_regex": None,
        "skipped_tests_baseline": 0,
        "local_ci": False,
        "ci_scope": "changed",
        "ci_skip": [],
    },
    "artifacts": {},
    "judges": {"research": False, "design": False, "plan": False, "code": True},
    "human": {"design_approval": "github-label:design-approved", "merge_before_deploy": False},
    "review_policy": {
        "core": {"human": "1+", "depth": "full"},
        "supporting": {"human": "author-ok", "depth": "reduced"},
        "generic": {"human": "skim", "depth": "minimal"},
    },
    "paths": {"runs": ".sdlc/runs", "principles": "docs/architecture/principles", "domain_map": ".sdlc/domain-map.yml"},
}


class ConfigError(ValueError):
    pass


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path=".sdlc/config.yml"):
    if not os.path.exists(path):
        raise ConfigError("%s not found. Run /sdlc:init first." % path)
    data = yamlish.load_file(path) or {}
    if not isinstance(data, dict):
        raise ConfigError("%s must be a map" % path)
    cfg = _merge(DEFAULTS, data)
    cfg["_path"] = path
    cfg["_root"] = os.path.dirname(os.path.dirname(os.path.abspath(path)))
    validate(cfg)
    return cfg


def validate(cfg):
    if cfg.get("version") != 1:
        raise ConfigError("version must be 1")
    for name, phases in (cfg.get("pipelines") or {}).items():
        if not isinstance(phases, list) or not phases:
            raise ConfigError("pipelines.%s must be a non-empty list" % name)
        unknown = [p for p in phases if p not in DEFAULT_PIPELINE]
        if unknown:
            raise ConfigError("pipelines.%s: unknown phases %s" % (name, unknown))
    if not isinstance(cfg["gates"].get("max_retries"), int) or cfg["gates"]["max_retries"] < 0:
        raise ConfigError("gates.max_retries must be a non-negative integer")
    if cfg["gates"].get("ci_scope") not in ("changed", "all"):
        raise ConfigError("gates.ci_scope must be changed or all")
    if not isinstance(cfg["gates"].get("ci_skip"), list):
        raise ConfigError("gates.ci_skip must be a list, e.g. [mutation]")
    if cfg["tracker"].get("type") not in ("jira", "none"):
        raise ConfigError("tracker.type must be jira or none")


def command(cfg, name):
    value = (cfg.get("commands") or {}).get(name)
    if value is None or str(value).strip() == "" or str(value).startswith("<"):
        return None
    return str(value)


def run_dir(cfg, key):
    return os.path.join(cfg["_root"], cfg["paths"]["runs"], key)
