"""Fluent API for module rules: ``modules()`` / ``no_modules()`` (Java: ``classes()`` / ``noClasses()``).

The grammar mirrors Java ArchUnit::

    modules().that().reside_in_a_package("shop.billing..")
        .and_().reside_outside_of_package("shop.billing.gateways..")
        .should().depend_on_modules_that().reside_in_a_package("libs.payments..")

    no_modules().that().reside_in_a_package("libs..")
        .should().transitively_depend_on_modules_that().reside_in_a_package("shop..")
        .or_should().depend_on_modules_that().reside_in_a_package("tests..")

One operation, one way:

- built-in selection/target — a fluent method: ``that().reside_in_a_package(...)``;
- composition (``not_``, ``or_`` inside a target, custom predicates) — a predicate argument:
  ``that(predicate)``, ``and_(predicate)``, ``or_(predicate)``, ``depend_on_modules_that(predicate)``;
- custom condition — ``should(condition)``, ``and_should(condition)``, ``or_should(condition)``.

``and_``/``or_`` and ``and_should``/``or_should`` apply left to right without precedence (as in Java).
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, replace
from typing import Generic, Self, TypeVar, overload

from archunit.lang import module_predicates as p
from archunit.core.graph import ImportGraph
from archunit.core.model import Module
from archunit.lang.conditions import (
    ArchCondition,
    ConditionEvent,
    DependencyCondition,
    DependencyKind,
    EvaluationContext,
    holds,
)
from archunit.lang.predicates import DescribedPredicate
from archunit.lang.rule import (
    ArchRule,
    EmptyRuleError,
    EvaluationResult,
    IgnoredHit,
    RuleSettings,
    Violation,
    describe,
)

R = TypeVar("R")


class Quantifier(enum.Enum):
    ALL = "modules"
    NONE = "no modules"


class Join(enum.Enum):
    AND = "and"
    OR = "or"


class ModulesPredicates(abc.ABC, Generic[R]):
    """Built-in module predicates shared by selection (``that()``) and targets (``..._modules_that()``)."""

    @abc.abstractmethod
    def _add(self, predicate: DescribedPredicate[Module]) -> R: ...

    def reside_in_a_package(self, pattern: str) -> R:
        return self._add(p.reside_in_a_package(pattern))

    def reside_in_any_package(self, *patterns: str) -> R:
        return self._add(p.reside_in_any_package(*patterns))

    def reside_outside_of_package(self, pattern: str) -> R:
        return self._add(p.reside_outside_of_package(pattern))

    def reside_outside_of_packages(self, *patterns: str) -> R:
        return self._add(p.reside_outside_of_packages(*patterns))

    def have_name_matching(self, regex: str) -> R:
        return self._add(p.have_name_matching(regex))


# --- rule ---


@dataclass(frozen=True, slots=True)
class ModuleRule(ArchRule):
    """"<quantifier> modules that <selection> should <condition> [and/or should <condition>]*".

    ``modules()`` is violated when the condition does not hold; ``no_modules()`` when it does.
    An empty selection raises ``EmptyRuleError`` unless ``allow_empty_should(True)`` is set.
    """

    quantifier: Quantifier
    selection: DescribedPredicate[Module] | None  # None means all analyzed modules
    conditions: tuple[tuple[Join | None, ArchCondition[Module]], ...]
    settings: RuleSettings = RuleSettings()

    @property
    def description(self) -> str:
        subject = self.quantifier.value
        if self.selection is not None:
            subject = f"{subject} that {self.selection.description}"
        parts = [
            f"should {condition.description}" if join is None else f"{join.value} should {condition.description}"
            for join, condition in self.conditions
        ]
        return describe(f"{subject} {' '.join(parts)}", self.settings)

    def _with_settings(self, settings: RuleSettings) -> Self:
        return replace(self, settings=settings)

    @overload
    def and_should(self) -> ModulesShould: ...
    @overload
    def and_should(self, condition: ArchCondition[Module]) -> ModuleRule: ...
    def and_should(self, condition: ArchCondition[Module] | None = None) -> ModulesShould | ModuleRule:
        return self._continue(Join.AND, condition)

    @overload
    def or_should(self) -> ModulesShould: ...
    @overload
    def or_should(self, condition: ArchCondition[Module]) -> ModuleRule: ...
    def or_should(self, condition: ArchCondition[Module] | None = None) -> ModulesShould | ModuleRule:
        return self._continue(Join.OR, condition)

    def _continue(self, join: Join, condition: ArchCondition[Module] | None) -> ModulesShould | ModuleRule:
        should = ModulesShould(self, join)
        return should if condition is None else should._complete(condition)

    def evaluate(self, graph: ImportGraph) -> EvaluationResult:
        selected = [
            module for module in graph.modules() if self.selection is None or self.selection.test(module)
        ]
        if not selected and not self.settings.allow_empty:
            raise EmptyRuleError(f"rule selected no modules: {self.description}")
        if not self.conditions:
            raise ValueError(f"rule has no conditions: {self.description}")
        context = EvaluationContext(
            graph,
            selected=frozenset(module.name for module in selected),
            ignored=self.settings.ignored_dependencies,
        )
        violations = [violation for module in selected for violation in self._check(module, context)]
        return EvaluationResult(
            self.description,
            tuple(violations),
            tuple(IgnoredHit(dependency, edge) for dependency, edge in context.ignored_hits),
        )

    def _check(self, module: Module, context: EvaluationContext) -> list[Violation]:
        """Conditions combine left to right; for ``no_modules()`` the rule is violated if the result holds.

        Violations report the events responsible for the outcome: violated events for ``modules()``,
        satisfied events for ``no_modules()``.
        """
        result: bool | None = None
        culprits: list[ConditionEvent] = []
        for join, condition in self.conditions:
            events = list(condition.check(module, context))
            value = holds(events)
            if result is None:
                result = value
            elif join is Join.AND:
                result = result and value
            else:
                result = result or value
            if self.quantifier is Quantifier.ALL:
                culprits.extend(event for event in events if not event.satisfied)
            elif value:
                culprits.extend(event for event in events if event.satisfied)
        violated = not result if self.quantifier is Quantifier.ALL else bool(result)
        if not violated:
            return []
        return [self._violation(context, event) for event in culprits]

    @staticmethod
    def _violation(context: EvaluationContext, event: ConditionEvent) -> Violation:
        location = context.graph.module(event.chain[0].importer) if event.chain else event.item
        line = event.chain[0].line if event.chain else None
        return Violation(event.message, location.path, line, event.chain)


# --- should ---


@dataclass(frozen=True, slots=True)
class ModulesShould:
    """Built-in conditions. ``base`` is the rule the next condition is joined to via ``join``."""

    base: ModuleRule
    join: Join | None = None

    def _complete(self, condition: ArchCondition[Module]) -> ModuleRule:
        rule = replace(self.base, conditions=(*self.base.conditions, (self.join, condition)))
        return rule

    def _dependency(self, kind: DependencyKind, predicate: DescribedPredicate[Module] | None) -> ModulesTarget | ModuleRule:
        target = ModulesTarget(self, kind)
        return target if predicate is None else target._add(predicate)

    @overload
    def depend_on_modules_that(self) -> ModulesTarget: ...
    @overload
    def depend_on_modules_that(self, predicate: DescribedPredicate[Module]) -> ModuleRule: ...
    def depend_on_modules_that(self, predicate: DescribedPredicate[Module] | None = None) -> ModulesTarget | ModuleRule:
        """A direct import into the target (Java: ``dependOnClassesThat``)."""
        return self._dependency(DependencyKind.DEPEND_ON, predicate)

    @overload
    def transitively_depend_on_modules_that(self) -> ModulesTarget: ...
    @overload
    def transitively_depend_on_modules_that(self, predicate: DescribedPredicate[Module]) -> ModuleRule: ...
    def transitively_depend_on_modules_that(
        self, predicate: DescribedPredicate[Module] | None = None
    ) -> ModulesTarget | ModuleRule:
        """The target is reachable through an import chain (Java: ``transitivelyDependOnClassesThat``)."""
        return self._dependency(DependencyKind.TRANSITIVELY_DEPEND_ON, predicate)

    @overload
    def only_depend_on_modules_that(self) -> ModulesTarget: ...
    @overload
    def only_depend_on_modules_that(self, predicate: DescribedPredicate[Module]) -> ModuleRule: ...
    def only_depend_on_modules_that(
        self, predicate: DescribedPredicate[Module] | None = None
    ) -> ModulesTarget | ModuleRule:
        """Every direct import goes into the target (Java: ``onlyDependOnClassesThat``)."""
        return self._dependency(DependencyKind.ONLY_DEPEND_ON, predicate)

    def only_be_accessed(self) -> OnlyBeAccessed:
        """Java: ``onlyBeAccessed()``."""
        return OnlyBeAccessed(self)


@dataclass(frozen=True, slots=True)
class OnlyBeAccessed:
    should: ModulesShould

    @overload
    def by_modules_that(self) -> ModulesTarget: ...
    @overload
    def by_modules_that(self, predicate: DescribedPredicate[Module]) -> ModuleRule: ...
    def by_modules_that(self, predicate: DescribedPredicate[Module] | None = None) -> ModulesTarget | ModuleRule:
        """Every direct importer matches the target (Java: ``onlyBeAccessed().byClassesThat``)."""
        return self.should._dependency(DependencyKind.ONLY_BE_ACCESSED_BY, predicate)


@dataclass(frozen=True, slots=True)
class ModulesTarget(ModulesPredicates[ModuleRule]):
    """Target of a built-in condition: ``...depend_on_modules_that().<predicate>``."""

    should: ModulesShould
    kind: DependencyKind

    def _add(self, predicate: DescribedPredicate[Module]) -> ModuleRule:
        return self.should._complete(DependencyCondition(self.kind, predicate))


# --- given / that ---


@dataclass(frozen=True, slots=True)
class ModulesThat(ModulesPredicates["GivenModulesConjunction"]):
    """Built-in selection predicates: ``modules().that().<predicate>``."""

    quantifier: Quantifier
    previous: DescribedPredicate[Module] | None = None
    join: Join = Join.AND

    def _add(self, predicate: DescribedPredicate[Module]) -> GivenModulesConjunction:
        if self.previous is None:
            combined = predicate
        elif self.join is Join.AND:
            combined = self.previous.and_(predicate)
        else:
            combined = self.previous.or_(predicate)
        return GivenModulesConjunction(self.quantifier, combined)


@dataclass(frozen=True, slots=True)
class GivenModulesConjunction:
    quantifier: Quantifier
    selection: DescribedPredicate[Module]

    @overload
    def and_(self) -> ModulesThat: ...
    @overload
    def and_(self, predicate: DescribedPredicate[Module]) -> GivenModulesConjunction: ...
    def and_(self, predicate: DescribedPredicate[Module] | None = None) -> ModulesThat | GivenModulesConjunction:
        that = ModulesThat(self.quantifier, self.selection, Join.AND)
        return that if predicate is None else that._add(predicate)

    @overload
    def or_(self) -> ModulesThat: ...
    @overload
    def or_(self, predicate: DescribedPredicate[Module]) -> GivenModulesConjunction: ...
    def or_(self, predicate: DescribedPredicate[Module] | None = None) -> ModulesThat | GivenModulesConjunction:
        that = ModulesThat(self.quantifier, self.selection, Join.OR)
        return that if predicate is None else that._add(predicate)

    @overload
    def should(self) -> ModulesShould: ...
    @overload
    def should(self, condition: ArchCondition[Module]) -> ModuleRule: ...
    def should(self, condition: ArchCondition[Module] | None = None) -> ModulesShould | ModuleRule:
        return _should(self.quantifier, self.selection, condition)


@dataclass(frozen=True, slots=True)
class GivenModules:
    quantifier: Quantifier

    @overload
    def that(self) -> ModulesThat: ...
    @overload
    def that(self, predicate: DescribedPredicate[Module]) -> GivenModulesConjunction: ...
    def that(self, predicate: DescribedPredicate[Module] | None = None) -> ModulesThat | GivenModulesConjunction:
        that = ModulesThat(self.quantifier)
        return that if predicate is None else that._add(predicate)

    @overload
    def should(self) -> ModulesShould: ...
    @overload
    def should(self, condition: ArchCondition[Module]) -> ModuleRule: ...
    def should(self, condition: ArchCondition[Module] | None = None) -> ModulesShould | ModuleRule:
        """A rule on all analyzed modules, without selection."""
        return _should(self.quantifier, None, condition)


def _should(
    quantifier: Quantifier,
    selection: DescribedPredicate[Module] | None,
    condition: ArchCondition[Module] | None,
) -> ModulesShould | ModuleRule:
    should = ModulesShould(ModuleRule(quantifier, selection, conditions=()))
    return should if condition is None else should._complete(condition)


def modules() -> GivenModules:
    """Java: ``classes()``."""
    return GivenModules(Quantifier.ALL)


def no_modules() -> GivenModules:
    """Java: ``noClasses()``."""
    return GivenModules(Quantifier.NONE)
