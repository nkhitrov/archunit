"""Import graph of a project — the input every rule is evaluated against."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from archunit.core.importer import discover_modules, parse_imports, to_import
from archunit.core.model import Import, Module
from archunit.core.pattern import PackagePattern


class ImportGraph:
    """Immutable graph of modules and imports.

    Built once per run (``ImportGraph.build``) and shared by all rules. Every import counts, including
    those under ``if TYPE_CHECKING:`` and inside functions: they create the same dependency. The
    ``Import.type_checking`` / ``Import.lazy`` flags are for reporting only.

    External modules (stdlib, third-party packages, anything outside ``packages``) are nodes without
    outgoing edges.
    """

    def __init__(self, modules: Iterable[Module], imports: Iterable[Import]) -> None:
        self._modules: dict[str, Module] = {module.name: module for module in modules}
        self._out: dict[str, list[Import]] = {}
        self._in: dict[str, list[Import]] = {}
        for edge in imports:
            if edge.imported not in self._modules:
                self._modules[edge.imported] = Module(edge.imported, None, external=True)
            self._out.setdefault(edge.importer, []).append(edge)
            self._in.setdefault(edge.imported, []).append(edge)

    @classmethod
    def build(cls, packages: Sequence[str], *, source_roots: Sequence[Path], exclude: Iterable[str] = ()) -> ImportGraph:
        """Parse ``packages`` found in ``source_roots``; ``exclude`` lists patterns of modules to drop.

        An excluded module disappears from the graph entirely, together with its incoming and outgoing edges.
        """
        excluded = tuple(PackagePattern(pattern) for pattern in exclude)

        def is_excluded(name: str) -> bool:
            return any(pattern.matches(name) for pattern in excluded)

        modules = [
            module
            for package in packages
            for module in discover_modules(package, source_roots)
            if not is_excluded(module.name)
        ]
        known = frozenset(module.name for module in modules)
        imports = [
            edge
            for module in modules
            for raw in parse_imports(module)
            if (edge := to_import(module, raw, known)).imported != module.name and not is_excluded(edge.imported)
        ]
        return cls(modules, imports)

    def module(self, name: str) -> Module:
        return self._modules[name]

    def modules(self, *, include_external: bool = False) -> Iterable[Module]:
        """All modules of the graph (only analyzed ones by default)."""
        return [module for module in self._modules.values() if include_external or not module.external]

    def imports_of(self, module: str) -> Sequence[Import]:
        """Direct imports of the module."""
        return tuple(self._out.get(module, ()))

    def importers_of(self, module: str) -> Sequence[Import]:
        """Direct imports pointing to the module."""
        return tuple(self._in.get(module, ()))

    def find_chain(
        self,
        source: str,
        target: Callable[[Module], bool],
        edge_filter: Callable[[Import], bool] = lambda _: True,
    ) -> Sequence[Import] | None:
        """Shortest import chain from ``source`` to any module matching ``target``; None if unreachable.

        ``edge_filter`` selects the edges that may be walked (rule exceptions).
        """
        previous: dict[str, Import] = {}
        visited = {source}
        queue = deque([source])
        while queue:
            current = queue.popleft()
            for edge in self._out.get(current, ()):
                if edge.imported in visited or not edge_filter(edge):
                    continue
                visited.add(edge.imported)
                previous[edge.imported] = edge
                if target(self._modules[edge.imported]):
                    return _unwind(previous, edge.imported, source)
                queue.append(edge.imported)
        return None


def _unwind(previous: dict[str, Import], end: str, source: str) -> tuple[Import, ...]:
    chain: list[Import] = []
    node = end
    while node != source:
        edge = previous[node]
        chain.append(edge)
        node = edge.importer
    return tuple(reversed(chain))
