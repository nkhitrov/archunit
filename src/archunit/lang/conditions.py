"""Conditions — ``ArchCondition`` from Java ArchUnit.

A condition checks one selected item and reports events: satisfied or violated, with a message and an
import chain. The rule quantifier decides what counts as a violation: violated events for ``modules()``,
satisfied events for ``no_modules()`` (Java: ``never``).

Built-in conditions are created only through the fluent chain ``should().depend_on_modules_that()...``.
A custom condition is a subclass of ``ArchCondition`` implementing ``check``, passed to ``should(...)`` /
``and_should(...)`` / ``or_should(...)``.
"""

from __future__ import annotations

import abc
import enum
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from archunit.core.graph import ImportGraph
from archunit.core.model import Import, Module
from archunit.core.pattern import PackagePattern
from archunit.lang.predicates import DescribedPredicate
from archunit.lang.rule import IgnoredDependency

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ConditionEvent:
    """Result of checking a condition on an item (Java: ``SimpleConditionEvent``)."""

    item: Module
    satisfied: bool
    message: str
    chain: tuple[Import, ...] = ()


def describe_import(edge: Import) -> str:
    """``a imports b`` marked with ``TYPE_CHECKING`` / ``lazy`` to show where the dependency comes from."""
    marks = [mark for flag, mark in ((edge.type_checking, "TYPE_CHECKING"), (edge.lazy, "lazy")) if flag]
    suffix = f" [{', '.join(marks)}]" if marks else ""
    return f"{edge.importer} imports {edge.imported}{suffix}"


@dataclass(slots=True)
class EvaluationContext:
    """What a condition can access while checking.

    Imports matched by the rule's ``ignore_dependency`` are invisible to conditions; each skip is recorded
    in ``ignored_hits`` for the report.
    """

    graph: ImportGraph
    selected: frozenset[str] = frozenset()  # modules selected by the rule
    ignored: Sequence[IgnoredDependency] = ()
    ignored_hits: list[tuple[IgnoredDependency, Import]] = field(default_factory=list)
    _compiled: tuple[tuple[IgnoredDependency, PackagePattern, PackagePattern], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._compiled = tuple((rule, PackagePattern(rule.source), PackagePattern(rule.target)) for rule in self.ignored)

    def is_visible(self, edge: Import) -> bool:
        for rule, source, target in self._compiled:
            if source.matches(edge.importer) and target.matches(edge.imported):
                if (rule, edge) not in self.ignored_hits:
                    self.ignored_hits.append((rule, edge))
                return False
        return True

    def module(self, name: str) -> Module:
        return self.graph.module(name)

    def imports_of(self, module: str) -> list[Import]:
        return [edge for edge in self.graph.imports_of(module) if self.is_visible(edge)]

    def importers_of(self, module: str) -> list[Import]:
        return [edge for edge in self.graph.importers_of(module) if self.is_visible(edge)]

    def find_chain(self, source: str, target: Callable[[Module], bool]) -> Sequence[Import] | None:
        return self.graph.find_chain(source, target, self.is_visible)


class ArchCondition(abc.ABC, Generic[T]):
    """Base class of conditions. ``description`` goes into the rule text after ``should``.

    A condition holds for an item if none of its events is violated.
    """

    description: str

    def __init__(self, description: str) -> None:
        self.description = description

    @abc.abstractmethod
    def check(self, item: T, context: EvaluationContext) -> Iterable[ConditionEvent]:
        """Events for the item. For ``no_modules()`` satisfied events become violations."""

    def and_(self, other: ArchCondition[T]) -> ArchCondition[T]:
        return _AndCondition(self, other)

    def or_(self, other: ArchCondition[T]) -> ArchCondition[T]:
        return _OrCondition(self, other)


def holds(events: Sequence[ConditionEvent]) -> bool:
    return all(event.satisfied for event in events)


class _AndCondition(ArchCondition[T]):
    def __init__(self, left: ArchCondition[T], right: ArchCondition[T]) -> None:
        super().__init__(f"{left.description} and {right.description}")
        self.left, self.right = left, right

    def check(self, item: T, context: EvaluationContext) -> Iterable[ConditionEvent]:
        return [*self.left.check(item, context), *self.right.check(item, context)]


class _OrCondition(ArchCondition[T]):
    def __init__(self, left: ArchCondition[T], right: ArchCondition[T]) -> None:
        super().__init__(f"{left.description} or {right.description}")
        self.left, self.right = left, right

    def check(self, item: T, context: EvaluationContext) -> Iterable[ConditionEvent]:
        left = list(self.left.check(item, context))
        if holds(left):
            return left
        right = list(self.right.check(item, context))
        return right if holds(right) else [*left, *right]


class DependencyKind(enum.Enum):
    """Built-in dependency conditions. The value is the description text (as in Java)."""

    DEPEND_ON = "depend on modules that"  # Java: dependOnClassesThat
    TRANSITIVELY_DEPEND_ON = "transitively depend on modules that"  # Java: transitivelyDependOnClassesThat
    ONLY_DEPEND_ON = "only depend on modules that"  # Java: onlyDependOnClassesThat
    ONLY_BE_ACCESSED_BY = "only be accessed by modules that"  # Java: onlyBeAccessed().byClassesThat


class DependencyCondition(ArchCondition[Module]):
    """A condition on the imports of a module.

    - ``DEPEND_ON`` — one event per direct import into the target; if there is none, one violated event.
    - ``TRANSITIVELY_DEPEND_ON`` — the target is reachable through a chain; the event carries the shortest one.
    - ``ONLY_DEPEND_ON`` — every direct import goes into the target, including stdlib and third-party
      packages (as in Java, where ``java..`` has to be allowed explicitly). To leave external modules
      unrestricted, add ``.or_(reside_outside_of_package("<project root>.."))`` to the target.
    - ``ONLY_BE_ACCESSED_BY`` — every direct importer of the module matches the target; imports between
      modules selected by the same rule are allowed.
    """

    def __init__(self, kind: DependencyKind, target: DescribedPredicate[Module]) -> None:
        super().__init__(f"{kind.value} {target.description}")
        self.kind = kind
        self.target = target

    def check(self, item: Module, context: EvaluationContext) -> Iterable[ConditionEvent]:
        match self.kind:
            case DependencyKind.DEPEND_ON:
                return self._depend_on(item, context)
            case DependencyKind.TRANSITIVELY_DEPEND_ON:
                return self._transitively_depend_on(item, context)
            case DependencyKind.ONLY_DEPEND_ON:
                return self._only_depend_on(item, context)
            case DependencyKind.ONLY_BE_ACCESSED_BY:
                return self._only_be_accessed_by(item, context)

    def _matches(self, name: str, context: EvaluationContext) -> bool:
        return self.target.test(context.module(name))

    def _depend_on(self, item: Module, context: EvaluationContext) -> list[ConditionEvent]:
        hits = [edge for edge in context.imports_of(item.name) if self._matches(edge.imported, context)]
        if not hits:
            return [ConditionEvent(item, False, f"{item.name} does not {self.description}")]
        return [ConditionEvent(item, True, describe_import(edge), (edge,)) for edge in hits]

    def _transitively_depend_on(self, item: Module, context: EvaluationContext) -> list[ConditionEvent]:
        chain = context.find_chain(item.name, self.target.test)
        if chain is None:
            return [ConditionEvent(item, False, f"{item.name} does not {self.description}")]
        path = " -> ".join([item.name, *(edge.imported for edge in chain)])
        return [ConditionEvent(item, True, f"{item.name} transitively imports {chain[-1].imported} via {path}", tuple(chain))]

    def _only_depend_on(self, item: Module, context: EvaluationContext) -> list[ConditionEvent]:
        bad = [edge for edge in context.imports_of(item.name) if not self._matches(edge.imported, context)]
        if not bad:
            return [ConditionEvent(item, True, f"{item.name} {self.description}")]
        return [ConditionEvent(item, False, describe_import(edge), (edge,)) for edge in bad]

    def _only_be_accessed_by(self, item: Module, context: EvaluationContext) -> list[ConditionEvent]:
        bad = [
            edge
            for edge in context.importers_of(item.name)
            if edge.importer not in context.selected and not self._matches(edge.importer, context)
        ]
        if not bad:
            return [ConditionEvent(item, True, f"{item.name} is accessed only by modules that {self.target.description}")]
        return [ConditionEvent(item, False, describe_import(edge), (edge,)) for edge in bad]
