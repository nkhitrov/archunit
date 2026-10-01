"""Collects module imports by static parsing (``ast``) without executing project code."""

from __future__ import annotations

import ast
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from archunit.core.model import Import, ImportKind, Module


class PackageNotFoundError(Exception):
    """A root package was not found in any source root."""


def discover_modules(package: str, source_roots: Sequence[Path]) -> list[Module]:
    """All modules of ``package``: ``*.py`` files and package directories (regular or namespace)."""
    relative = Path(*package.split("."))
    for root in source_roots:
        directory = root / relative
        if directory.is_dir():
            return sorted(_walk(directory, package), key=lambda module: module.name)
        single = directory.with_suffix(".py")
        if single.is_file():
            return [Module(package, single)]
    raise PackageNotFoundError(f"package {package!r} not found in {[str(root) for root in source_roots]}")


def _walk(directory: Path, name: str) -> Iterator[Module]:
    init = directory / "__init__.py"
    yield Module(name, init if init.is_file() else None, is_package=True)
    for child in sorted(directory.iterdir()):
        if child.is_dir() and child.name.isidentifier() and any(child.rglob("*.py")):
            yield from _walk(child, f"{name}.{child.name}")
        elif child.suffix == ".py" and child.stem.isidentifier() and child.name != "__init__.py":
            yield Module(f"{name}.{child.stem}", child)


@dataclass(frozen=True, slots=True)
class RawImport:
    """An import before it is resolved to a graph module name.

    ``candidates`` are names in order of preference: for ``from a import b`` first ``a.b`` (if it is a
    submodule), then ``a``.
    """

    candidates: tuple[str, ...]
    line: int
    kind: ImportKind
    type_checking: bool
    lazy: bool


def parse_imports(module: Module) -> list[RawImport]:
    if module.path is None:
        return []
    tree = ast.parse(module.path.read_bytes(), filename=str(module.path))
    collector = _Collector(module)
    collector.visit(tree)
    return collector.imports


def to_import(module: Module, raw: RawImport, known: frozenset[str]) -> Import:
    """Pick the target name: the first candidate known to the graph, otherwise the most general one."""
    target = next((name for name in raw.candidates if name in known), raw.candidates[-1])
    return Import(module.name, target, raw.line, raw.kind, raw.type_checking, raw.lazy)


class _Collector(ast.NodeVisitor):
    def __init__(self, module: Module) -> None:
        self.module = module
        self.imports: list[RawImport] = []
        self._function_depth = 0
        self._type_checking_depth = 0

    # --- context ---

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._in_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._in_function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._in_function(node)

    def _in_function(self, node: ast.AST) -> None:
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_If(self, node: ast.If) -> None:
        if not _is_type_checking(node.test):
            self.generic_visit(node)
            return
        self.visit(node.test)
        self._type_checking_depth += 1
        for child in node.body:
            self.visit(child)
        self._type_checking_depth -= 1
        for child in node.orelse:
            self.visit(child)

    # --- imports ---

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._add((alias.name,), node, ImportKind.IMPORT)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = self._resolve_base(node)
        if base is None:
            return
        for alias in node.names:
            if alias.name == "*":
                self._add((base,), node, ImportKind.FROM)
            else:
                self._add((f"{base}.{alias.name}", base), node, ImportKind.FROM)

    def _resolve_base(self, node: ast.ImportFrom) -> str | None:
        if node.level == 0:
            return node.module
        parts = self.module.name.split(".")
        if not self.module.is_package:
            parts = parts[:-1]
        drop = node.level - 1
        if drop > len(parts) - 1:
            return None  # goes beyond the root package
        anchor = parts[: len(parts) - drop]
        return ".".join([*anchor, node.module] if node.module else anchor)

    def _add(self, candidates: tuple[str, ...], node: ast.stmt, kind: ImportKind) -> None:
        self.imports.append(
            RawImport(
                candidates=candidates,
                line=node.lineno,
                kind=kind,
                type_checking=self._type_checking_depth > 0,
                lazy=self._function_depth > 0,
            )
        )


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False
