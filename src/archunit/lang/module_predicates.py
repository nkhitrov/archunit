"""Module predicates — the counterpart of ``JavaClass.Predicates`` from Java ArchUnit.

Used where the fluent chain is not enough: composition via ``and_``/``or_``/``not_`` and passing to
``that(...)``, ``and_(...)``, ``or_(...)``, ``depend_on_modules_that(...)`` etc.
"""

from __future__ import annotations

import re

from archunit.core.model import Module
from archunit.core.pattern import PackagePattern
from archunit.lang.predicates import DescribedPredicate, not_


def _quoted(patterns: tuple[str, ...]) -> str:
    return ", ".join(f"'{p}'" for p in patterns)


def reside_in_a_package(pattern: str) -> DescribedPredicate[Module]:
    compiled = PackagePattern(pattern)
    return DescribedPredicate(f"reside in a package '{pattern}'", lambda m: compiled.matches(m.name))


def reside_in_any_package(*patterns: str) -> DescribedPredicate[Module]:
    compiled = tuple(PackagePattern(p) for p in patterns)
    return DescribedPredicate(
        f"reside in any package [{_quoted(patterns)}]",
        lambda m: any(p.matches(m.name) for p in compiled),
    )


def reside_outside_of_package(pattern: str) -> DescribedPredicate[Module]:
    return not_(reside_in_a_package(pattern)).as_(f"reside outside of package '{pattern}'")


def reside_outside_of_packages(*patterns: str) -> DescribedPredicate[Module]:
    return not_(reside_in_any_package(*patterns)).as_(f"reside outside of packages [{_quoted(patterns)}]")


def have_name_matching(regex: str) -> DescribedPredicate[Module]:
    """The fully qualified module name fully matches the regular expression."""
    compiled = re.compile(regex)
    return DescribedPredicate(f"have name matching '{regex}'", lambda m: compiled.fullmatch(m.name) is not None)
