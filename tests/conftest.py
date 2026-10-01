from pathlib import Path

import pytest

from archunit import ImportGraph

FIXTURES = Path(__file__).parent / "fixtures" / "projects"
EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture(scope="session")
def deps_graph() -> ImportGraph:
    """app.a.x -> app.a.y -> app.b.z -> sqlalchemy; app.c.w -> app.a.x; app.d.v -> app.b.z, lazy -> app.c.w."""
    return ImportGraph.build(["app"], source_roots=[FIXTURES / "deps"])
