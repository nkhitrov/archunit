"""Module predicates — the counterpart of ``JavaClass.Predicates`` from Java ArchUnit.

Used where the fluent chain is not enough: composition via ``and_``/``or_``/``not_`` and passing to
``that(...)``, ``and_(...)``, ``or_(...)``, ``depend_on_modules_that(...)`` etc.
"""

from archunit.lang.module_predicates import (
    have_name_matching,
    reside_in_a_package,
    reside_in_any_package,
    reside_outside_of_package,
    reside_outside_of_packages,
)
from archunit.lang.predicates import DescribedPredicate, not_

__all__ = [
    "DescribedPredicate",
    "have_name_matching",
    "not_",
    "reside_in_a_package",
    "reside_in_any_package",
    "reside_outside_of_package",
    "reside_outside_of_packages",
]
