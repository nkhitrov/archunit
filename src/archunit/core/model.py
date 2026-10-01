"""Model of the analyzed code: modules and imports between them.

The model is built statically (``ast``); project code is never imported.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path


class ImportKind(enum.Enum):
    """Syntactic form of an import."""

    IMPORT = "import"  # import a.b
    FROM = "from"  # from a import b / from . import b


@dataclass(frozen=True, slots=True)
class Module:
    """A Python module (file) or package (``__init__.py``).

    ``external=True`` marks a module outside the analyzed packages (stdlib, third-party libraries).
    External modules appear in the graph as import targets, but their own imports are not analyzed.
    """

    name: str  # fully qualified name: "shop.features.core.orders.use_cases"
    path: Path | None  # None for external modules
    is_package: bool = False
    external: bool = False


@dataclass(frozen=True, slots=True)
class Import:
    """Graph edge: ``importer`` imports ``imported``.

    ``imported`` is always a module name: ``from a.b import C`` (C is an object) yields an edge to ``a.b``,
    ``from a import b`` (b is a submodule) yields ``a.b``. Relative imports are resolved to absolute ones.
    """

    importer: str
    imported: str
    line: int
    kind: ImportKind
    # Reporting flags only; they never affect checks — such an import is still a dependency.
    type_checking: bool = False  # inside ``if TYPE_CHECKING:``
    lazy: bool = False  # inside a function/method rather than at module level
