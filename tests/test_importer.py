from pathlib import Path

import pytest

from archunit import ImportGraph
from archunit.core.importer import PackageNotFoundError
from tests.conftest import FIXTURES

ROOT = FIXTURES / "imports"


@pytest.fixture(scope="module")
def graph() -> ImportGraph:
    return ImportGraph.build(["pkg"], source_roots=[ROOT])


def edges(graph: ImportGraph, module: str) -> list[tuple[str, int, bool, bool]]:
    return [(e.imported, e.line, e.type_checking, e.lazy) for e in graph.imports_of(module)]


def test_modules_discovered_including_namespace_packages(graph: ImportGraph) -> None:
    assert {m.name: m.is_package for m in graph.modules()} == {
        "pkg": True,
        "pkg.namespace": True,
        "pkg.namespace.inner": False,
        "pkg.sibling": False,
        "pkg.star": False,
        "pkg.sub": True,
        "pkg.sub.deep": False,
    }


def test_import_forms_resolve_to_modules(graph: ImportGraph) -> None:
    assert edges(graph, "pkg.sibling") == [
        ("os.path", 1, False, False),  # import a.b — external module
        ("pkg.sub.deep", 2, False, False),  # import a.b.c
        ("pkg.sub.deep", 3, False, False),  # from pkg.sub import deep — submodule
        ("pkg.sub", 3, False, False),  # from pkg.sub import OBJECT — object => package
        ("pkg.sub.deep", 4, False, False),  # from .sub.deep import VALUE — relative
        # from .. import outside — goes beyond the root package, dropped
        ("pkg.star", 6, False, False),  # from x import *
    ]


def test_relative_imports_from_package_init(graph: ImportGraph) -> None:
    assert edges(graph, "pkg") == [("pkg.sub", 1, False, False), ("pkg.sibling", 2, False, False)]
    assert edges(graph, "pkg.namespace.inner") == [("pkg.sub.deep", 1, False, False)]


def test_type_checking_and_lazy_imports_are_dependencies(graph: ImportGraph) -> None:
    assert edges(graph, "pkg.sub.deep") == [
        ("typing", 1, False, False),
        ("typing", 2, False, False),
        ("pkg.star", 5, True, False),  # if TYPE_CHECKING:
        ("pkg.sibling", 7, True, False),  # if typing.TYPE_CHECKING:
        ("json", 9, False, False),  # else branch — a regular import
        ("pkg.star", 15, False, True),  # inside a function
        ("pkg.sub", 21, False, True),  # inside a method
    ]


def test_external_modules_are_leaf_nodes(graph: ImportGraph) -> None:
    external = {m.name for m in graph.modules(include_external=True) if m.external}
    assert external == {"os.path", "typing", "json"}
    assert all(graph.module(name).path is None for name in external)
    assert graph.importers_of("json")[0].importer == "pkg.sub.deep"


def test_exclude_drops_module_with_its_edges() -> None:
    graph = ImportGraph.build(["pkg"], source_roots=[ROOT], exclude=["pkg.star"])
    assert "pkg.star" not in {m.name for m in graph.modules(include_external=True)}
    assert all(e.imported != "pkg.star" for e in graph.imports_of("pkg.sibling"))


def test_missing_package_is_an_error() -> None:
    with pytest.raises(PackageNotFoundError):
        ImportGraph.build(["nope"], source_roots=[Path(ROOT)])


def test_find_chain_returns_shortest_path(deps_graph: ImportGraph) -> None:
    chain = deps_graph.find_chain("app.c.w", lambda m: m.name == "sqlalchemy")
    assert chain is not None
    assert [(e.importer, e.imported) for e in chain] == [
        ("app.c.w", "app.a.x"),
        ("app.a.x", "app.a.y"),
        ("app.a.y", "app.b.z"),
        ("app.b.z", "sqlalchemy"),
    ]
    assert deps_graph.find_chain("app.b.z", lambda m: m.name.startswith("app.c")) is None
