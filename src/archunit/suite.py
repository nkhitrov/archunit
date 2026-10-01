"""Rule suites — the counterpart of a Java ArchUnit test class with ``@AnalyzeClasses`` and ``@ArchTest`` fields.

::

    class TransportBoundary(ArchSuite):
        analyze = AnalyzeModules("shop", "libs")
        because = "transport is a gateway detail"

        def rule_libs_do_not_know_app(self) -> ArchRule:
            return (no_modules().that().reside_in_a_package("libs..")
                    .should().depend_on_modules_that().reside_in_a_package("shop.."))

Conventions:

- a rule is a public ``rule_*`` method without arguments returning an ``ArchRule`` (Java: ``@ArchTest``);
- methods starting with ``_`` are helpers, not rules; shared templates and suite parameters are class
  attributes available through ``self``; reuse works through suite inheritance;
- ``because`` on the class is the default for all rules of the suite; a rule's own ``because`` wins;
- ``include`` runs the rules of other suites as part of this one (Java: ``ArchTests.in``);
- rule id in the report: ``<Suite>::<method>``.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from dataclasses import dataclass
from typing import ClassVar

from archunit.lang.rule import ArchRule

RULE_PREFIX = "rule_"


@dataclass(frozen=True, slots=True)
class AnalyzeModules:
    """What to analyze (Java: ``@AnalyzeClasses``).

    ``packages`` are root packages; ``exclude`` lists patterns of modules dropped from the graph entirely
    (Java: ``ImportOption``, e.g. ``DoNotIncludeTests``). If a suite does not set it, ``[tool.archunit]``
    is used.
    """

    packages: tuple[str, ...]
    exclude: tuple[str, ...] = ()

    def __init__(self, *packages: str, exclude: tuple[str, ...] = ()) -> None:
        object.__setattr__(self, "packages", packages)
        object.__setattr__(self, "exclude", exclude)


@dataclass(frozen=True, slots=True)
class SuiteRule:
    """A suite rule. Built lazily (``build``) so an error in one method does not break the whole suite."""

    rule_id: str  # "TransportBoundary::rule_libs_do_not_know_app"
    suite: ArchSuite
    method: str
    analyze: AnalyzeModules | None  # of the rule's suite, else of the including suite, else None (config)

    def build(self) -> ArchRule:
        """Call the rule method and apply the suite's default ``because``."""
        rule = getattr(self.suite, self.method)()
        if not isinstance(rule, ArchRule):
            raise TypeError(f"{self.rule_id} must return ArchRule, got {type(rule).__name__}")
        because = type(self.suite).because
        if because is not None and rule.settings.because is None:
            rule = rule.because(because)
        return rule


class ArchSuite:
    analyze: ClassVar[AnalyzeModules | None] = None
    include: ClassVar[tuple[type[ArchSuite], ...]] = ()
    because: ClassVar[str | None] = None

    @classmethod
    def rule_names(cls) -> list[str]:
        """Rule method names in declaration order (inheritance included)."""
        names: list[str] = []
        for klass in reversed(cls.__mro__):
            for name, member in vars(klass).items():
                if name.startswith(RULE_PREFIX) and inspect.isfunction(member) and name not in names:
                    names.append(name)
        return names

    def rules(self) -> Iterator[SuiteRule]:
        """Rules of the suite and of ``include``.

        A suite included several times (including nested ``include``) runs once.
        """
        yield from _collect(type(self), None, set())


def _collect(suite: type[ArchSuite], inherited: AnalyzeModules | None, seen: set[type[ArchSuite]]) -> Iterator[SuiteRule]:
    if suite in seen:
        return
    seen.add(suite)
    analyze = suite.analyze or inherited
    instance = suite()
    for name in suite.rule_names():
        yield SuiteRule(f"{suite.__name__}::{name}", instance, name, analyze)
    for included in suite.include:
        yield from _collect(included, analyze, seen)
