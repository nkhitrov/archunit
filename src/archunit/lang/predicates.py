"""Described predicates — ``DescribedPredicate`` from Java ArchUnit.

A predicate carries a human-readable description; rule texts and violation messages are built from them.

Composition works as in Java::

    reside_in_a_package("shop.billing..").and_(not_(have_name_matching(r".*\\.events")))
    reside_in_a_package("shop.api..").or_(reside_in_a_package("shop.workers.."))

A custom predicate: ``DescribedPredicate.describe(description, function)`` (Java: ``DescribedPredicate.describe``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class DescribedPredicate(Generic[T]):
    __slots__ = ("_test", "description")

    def __init__(self, description: str, test: Callable[[T], bool]) -> None:
        self.description = description
        self._test = test

    @staticmethod
    def describe(description: str, test: Callable[[T], bool]) -> DescribedPredicate[T]:
        return DescribedPredicate(description, test)

    def test(self, item: T) -> bool:
        return self._test(item)

    def and_(self, other: DescribedPredicate[T]) -> DescribedPredicate[T]:
        return DescribedPredicate(
            f"{self.description} and {other.description}",
            lambda item: self.test(item) and other.test(item),
        )

    def or_(self, other: DescribedPredicate[T]) -> DescribedPredicate[T]:
        return DescribedPredicate(
            f"{self.description} or {other.description}",
            lambda item: self.test(item) or other.test(item),
        )

    def as_(self, description: str) -> DescribedPredicate[T]:
        """Replace the description (Java: ``as``)."""
        return DescribedPredicate(description, self._test)


def not_(predicate: DescribedPredicate[T]) -> DescribedPredicate[T]:
    """Java: ``DescribedPredicate.not``."""
    return DescribedPredicate(f"not {predicate.description}", lambda item: not predicate.test(item))
