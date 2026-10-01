"""Runner: discovers rule suites, builds graphs, evaluates rules and collects a report. No pytest."""

from __future__ import annotations

import importlib.util
import sys
import tomllib
import traceback
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from archunit.core.graph import ImportGraph
from archunit.lang.rule import EmptyRuleError, EvaluationResult
from archunit.suite import AnalyzeModules, ArchSuite, SuiteRule

RULE_FILES = "arch_*.py"


class ConfigError(Exception):
    """Invalid project configuration or rule files."""


@dataclass(frozen=True, slots=True)
class ArchunitConfig:
    """The ``[tool.archunit]`` section of ``pyproject.toml``.

    ::

        [tool.archunit]
        root_packages = ["shop", "libs"]   # what to analyze by default
        source_roots = ["."]              # where to find them (relative to the project)
        rules_dir = "arch"                # where rule suites live (arch_*.py)
        exclude = ["shop.migrations.versions.."]
    """

    project_dir: Path
    root_packages: tuple[str, ...]
    source_roots: tuple[Path, ...] = (Path(),)
    rules_dir: Path = Path("arch")
    exclude: tuple[str, ...] = ()

    @classmethod
    def load(cls, project_dir: Path) -> ArchunitConfig:
        pyproject = project_dir / "pyproject.toml"
        if not pyproject.is_file():
            raise ConfigError(f"{pyproject} not found")
        section = tomllib.loads(pyproject.read_text()).get("tool", {}).get("archunit")
        if section is None:
            raise ConfigError(f"[tool.archunit] section is missing in {pyproject}")
        unknown = set(section) - {"root_packages", "source_roots", "rules_dir", "exclude"}
        if unknown:
            raise ConfigError(f"unknown [tool.archunit] keys: {sorted(unknown)}")
        packages = section.get("root_packages")
        if not packages:
            raise ConfigError("[tool.archunit] root_packages is required")
        return cls(
            project_dir=project_dir,
            root_packages=tuple(packages),
            source_roots=tuple(project_dir / root for root in section.get("source_roots", ["."])),
            rules_dir=project_dir / section.get("rules_dir", "arch"),
            exclude=tuple(section.get("exclude", ())),
        )


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    rule_id: str
    description: str
    result: EvaluationResult | None = None
    error: str | None = None  # empty selection, exception in a rule, graph error


@dataclass(frozen=True, slots=True)
class Report:
    outcomes: tuple[RuleOutcome, ...] = field(default=())
    errors: tuple[str, ...] = ()  # errors not tied to a rule (loading rule files)

    @property
    def exit_code(self) -> int:
        """0 — all passed, 1 — violations, 2 — errors (take precedence over violations)."""
        if self.errors or any(o.error for o in self.outcomes):
            return 2
        if any(o.result and not o.result.passed for o in self.outcomes):
            return 1
        return 0


def discover_suites(rules_dir: Path) -> Sequence[type[ArchSuite]]:
    """Import ``rules_dir/arch_*.py`` and return the root suites.

    A root suite is declared in a rule file and not included (``include``) by another discovered suite:
    included suites run as part of the including one. Suites without rules and without ``include``
    (base classes with helpers) are skipped.
    """
    if not rules_dir.is_dir():
        raise ConfigError(f"rules dir {rules_dir} not found")
    suites: list[type[ArchSuite]] = []
    for path in sorted(rules_dir.glob(RULE_FILES)):
        module_name = f"_archunit_rules.{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ConfigError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        suites.extend(
            obj
            for obj in vars(module).values()
            if isinstance(obj, type)
            and issubclass(obj, ArchSuite)
            and obj.__module__ == module_name
            and (obj.rule_names() or obj.include)
        )
    included = {inc for suite in suites for inc in _all_included(suite)}
    return [suite for suite in suites if suite not in included]


def _all_included(suite: type[ArchSuite]) -> set[type[ArchSuite]]:
    result: set[type[ArchSuite]] = set()
    stack = list(suite.include)
    while stack:
        current = stack.pop()
        if current not in result:
            result.add(current)
            stack.extend(current.include)
    return result


def run(config: ArchunitConfig, *, select: str | None = None) -> Report:
    """Evaluate all suites; ``select`` is a substring of the rule id (``Suite::rule_method``)."""
    sys.path[:0] = [str(root) for root in config.source_roots]
    try:
        suites = discover_suites(config.rules_dir)
    except Exception:  # any error in a rule file is a run error, not a CLI crash
        return Report(errors=(traceback.format_exc(),))

    graphs: dict[AnalyzeModules, ImportGraph | str] = {}
    outcomes: list[RuleOutcome] = []
    for suite in suites:
        try:
            suite_rules = list(suite().rules())
        except Exception:
            outcomes.append(RuleOutcome(suite.__name__, "", error=traceback.format_exc()))
            continue
        for suite_rule in suite_rules:
            if select and select not in suite_rule.rule_id:
                continue
            analyze = suite_rule.analyze or AnalyzeModules(*config.root_packages)
            analyze = AnalyzeModules(*analyze.packages, exclude=(*config.exclude, *analyze.exclude))
            graph = graphs.get(analyze) or graphs.setdefault(analyze, _build(analyze, config))
            outcomes.append(_evaluate(suite_rule, graph))
    return Report(tuple(outcomes))


def _build(analyze: AnalyzeModules, config: ArchunitConfig) -> ImportGraph | str:
    try:
        return ImportGraph.build(analyze.packages, source_roots=config.source_roots, exclude=analyze.exclude)
    except Exception:
        return traceback.format_exc()


def _evaluate(suite_rule: SuiteRule, graph: ImportGraph | str) -> RuleOutcome:
    rule_id = suite_rule.rule_id
    try:
        rule = suite_rule.build()
    except Exception:
        return RuleOutcome(rule_id, "", error=traceback.format_exc())
    if isinstance(graph, str):
        return RuleOutcome(rule_id, rule.description, error=graph)
    try:
        return RuleOutcome(rule_id, rule.description, result=rule.evaluate(graph))
    except EmptyRuleError as error:
        return RuleOutcome(rule_id, rule.description, error=str(error))
    except Exception:
        return RuleOutcome(rule_id, rule.description, error=traceback.format_exc())
