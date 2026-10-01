"""Base contract of a rule and of its evaluation result."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Self

from archunit.core.graph import ImportGraph
from archunit.core.model import Import


@dataclass(frozen=True, slots=True)
class Violation:
    """A single violation.

    ``chain`` is the import path from the violator to the forbidden module: one edge for a direct import,
    several for a transitive one. ``key`` is stable across runs (no line numbers), reserved for
    baseline/freeze support.
    """

    message: str
    path: Path | None
    line: int | None
    chain: tuple[Import, ...] = ()

    @property
    def key(self) -> str:
        # messages contain no line numbers, so the key survives edits above the import
        return self.message


@dataclass(frozen=True, slots=True)
class IgnoredHit:
    """An import skipped by ``ignore_dependency``; reported together with the reason."""

    dependency: IgnoredDependency
    edge: Import


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    rule_description: str
    violations: tuple[Violation, ...] = ()
    ignored: tuple[IgnoredHit, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.violations


class EmptyRuleError(Exception):
    """``that()`` selected no modules and ``allow_empty_should(True)`` is not set (Java: ``failOnEmptyShould``)."""


@dataclass(frozen=True, slots=True)
class IgnoredDependency:
    """A targeted rule exception: imports ``source`` -> ``target`` are not violations."""

    source: str  # pattern of the importing module
    target: str  # pattern of the imported module
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RuleSettings:
    """Settings shared by all rules. Changed only through fluent methods, which return a copy."""

    name: str | None = None
    because: str | None = None
    allow_empty: bool = False
    ignored_dependencies: tuple[IgnoredDependency, ...] = field(default=())


class ArchRule(abc.ABC):
    """A rule is an immutable value.

    Every fluent method returns a new rule, so a template shared within a suite through ``self`` can be
    refined in place without affecting the shared part.
    """

    settings: RuleSettings

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Human-readable rule text (Java: ``ArchRule.getDescription``)."""

    @abc.abstractmethod
    def _with_settings(self, settings: RuleSettings) -> Self: ...

    @abc.abstractmethod
    def evaluate(self, graph: ImportGraph) -> EvaluationResult:
        """Evaluate the rule on the graph. An empty selection without ``allow_empty_should(True)`` raises ``EmptyRuleError``."""

    def because(self, reason: str) -> Self:
        return self._with_settings(replace(self.settings, because=reason))

    def as_(self, name: str) -> Self:
        """Replace the generated rule description with a custom name (Java: ``as``)."""
        return self._with_settings(replace(self.settings, name=name))

    def allow_empty_should(self, allow: bool) -> Self:
        """Allow the rule to select no modules (Java: ``allowEmptyShould``)."""
        return self._with_settings(replace(self.settings, allow_empty=allow))

    def ignore_dependency(self, source: str, target: str, *, reason: str) -> Self:
        """Imports from ``source`` to ``target`` (patterns) are not violations (Java: ``ignoreDependency``).

        The reason is mandatory and shows up in the report.
        """
        ignored = (*self.settings.ignored_dependencies, IgnoredDependency(source, target, reason))
        return self._with_settings(replace(self.settings, ignored_dependencies=ignored))


def describe(text: str, settings: RuleSettings) -> str:
    """Final description: the ``as_`` name or the generated text, plus ``because``."""
    base = settings.name or text
    return f"{base}, because {settings.because}" if settings.because else base
