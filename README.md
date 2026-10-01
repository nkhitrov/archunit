# archunit

Architecture rules for Python projects, inspired by [Java ArchUnit](https://www.archunit.org/):
rules are written in Python as a DSL and checked by a dedicated runner, without pytest.

```python
# arch/arch_imports.py
from archunit import ArchRule, ArchSuite, no_modules


class TransportBoundary(ArchSuite):
    def rule_libs_do_not_know_the_app(self) -> ArchRule:
        return (
            no_modules().that().reside_in_a_package("libs..")
            .should().transitively_depend_on_modules_that().reside_in_a_package("shop..")
            .because("a library that knows the domain is no longer a library")
        )
```

```toml
# pyproject.toml
[tool.archunit]
root_packages = ["shop", "libs"]
source_roots = ["src"]
```

```bash
archunit check .
```

Exit code: 0 — all rules hold, 1 — violations, 2 — errors (empty selection, broken rule, configuration).

Sample project — [`examples/shop`](examples/shop).
