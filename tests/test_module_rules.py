from collections.abc import Iterable

import pytest

from archunit import (
    ArchCondition,
    ArchRule,
    ConditionEvent,
    EmptyRuleError,
    EvaluationContext,
    ImportGraph,
    Module,
    modules,
    no_modules,
)
from archunit.predicates import (
    DescribedPredicate,
    have_name_matching,
    not_,
    reside_in_a_package,
    reside_in_any_package,
    reside_outside_of_package,
)

# Graph of the deps fixture:
#   app.a.x -> app.a.y -> app.b.z -> sqlalchemy
#   app.c.w -> app.a.x
#   app.d.v -> app.b.z, app.d.v -lazy-> app.c.w


def messages(rule: ArchRule, graph: ImportGraph) -> list[str]:
    return [v.message for v in rule.evaluate(graph).violations]


class TestDependOn:
    def test_no_modules_reports_each_forbidden_import(self, deps_graph: ImportGraph) -> None:
        rule = no_modules().that().reside_in_a_package("app.d..").should().depend_on_modules_that().reside_in_any_package(
            "app.b..", "app.c.."
        )
        assert messages(rule, deps_graph) == [
            "app.d.v imports app.b.z",
            "app.d.v imports app.c.w [lazy]",
        ]

    def test_direct_only_by_default(self, deps_graph: ImportGraph) -> None:
        rule = no_modules().that().reside_in_a_package("app.a.x").should().depend_on_modules_that().reside_in_a_package("app.b..")
        assert messages(rule, deps_graph) == []

    def test_modules_requires_dependency(self, deps_graph: ImportGraph) -> None:
        rule = modules().that().reside_in_a_package("app.a..").should().depend_on_modules_that().reside_in_a_package("app.b..")
        assert messages(rule, deps_graph) == [
            "app.a does not depend on modules that reside in a package 'app.b..'",
            "app.a.x does not depend on modules that reside in a package 'app.b..'",
        ]

    def test_violation_location_points_to_import_line(self, deps_graph: ImportGraph) -> None:
        rule = no_modules().that().reside_in_a_package("app.d.v").should().depend_on_modules_that().reside_in_a_package("app.c..")
        (violation,) = rule.evaluate(deps_graph).violations
        assert violation.path is not None
        assert (violation.path.name, violation.line) == ("v.py", 5)


class TestTransitivelyDependOn:
    def test_reports_shortest_chain(self, deps_graph: ImportGraph) -> None:
        rule = (
            no_modules().that().reside_in_a_package("app.c..")
            .should().transitively_depend_on_modules_that().have_name_matching("sqlalchemy")
        )
        (violation,) = rule.evaluate(deps_graph).violations
        assert violation.message == (
            "app.c.w transitively imports sqlalchemy via app.c.w -> app.a.x -> app.a.y -> app.b.z -> sqlalchemy"
        )
        assert len(violation.chain) == 4

    def test_unreachable_target_passes(self, deps_graph: ImportGraph) -> None:
        rule = no_modules().that().reside_in_a_package("app.b..").should().transitively_depend_on_modules_that().reside_in_a_package("app.c..")
        assert messages(rule, deps_graph) == []


class TestOnlyDependOn:
    def test_strict_like_java_checks_external_modules(self, deps_graph: ImportGraph) -> None:
        rule = modules().that().reside_in_a_package("app.b..").should().only_depend_on_modules_that().reside_in_a_package("app..")
        assert messages(rule, deps_graph) == ["app.b.z imports sqlalchemy"]

    def test_external_allowed_explicitly(self, deps_graph: ImportGraph) -> None:
        rule = (
            modules().that().reside_in_a_package("app.b..")
            .should().only_depend_on_modules_that(reside_in_a_package("app..").or_(reside_outside_of_package("app..")))
        )
        assert messages(rule, deps_graph) == []


class TestOnlyBeAccessedBy:
    def test_reports_foreign_importers(self, deps_graph: ImportGraph) -> None:
        rule = modules().that().reside_in_a_package("app.b..").should().only_be_accessed().by_modules_that().reside_in_a_package("app.a..")
        assert messages(rule, deps_graph) == ["app.d.v imports app.b.z"]

    def test_imports_inside_selection_allowed(self, deps_graph: ImportGraph) -> None:
        rule = modules().that().reside_in_a_package("app.a..").should().only_be_accessed().by_modules_that().reside_in_a_package("app.c..")
        assert messages(rule, deps_graph) == []


class TestConjunctions:
    def test_selection_and_or_left_to_right(self, deps_graph: ImportGraph) -> None:
        rule = (
            no_modules().that().reside_in_a_package("app.a..").or_().reside_in_a_package("app.d..")
            .and_().have_name_matching(r".*\.v")
            .should().depend_on_modules_that().reside_in_a_package("app.b..")
        )
        assert messages(rule, deps_graph) == ["app.d.v imports app.b.z"]

    def test_composed_predicate_as_argument(self, deps_graph: ImportGraph) -> None:
        rule = no_modules().that(reside_in_a_package("app..").and_(not_(reside_in_any_package("app.d..", "app.c..")))).should().depend_on_modules_that(
            reside_in_a_package("app..").and_(not_(reside_in_a_package("app.a..")))
        )
        assert messages(rule, deps_graph) == ["app.a.y imports app.b.z"]

    def test_or_should_never_either(self, deps_graph: ImportGraph) -> None:
        rule = (
            no_modules().that().reside_in_a_package("app.d..")
            .should().depend_on_modules_that().reside_in_a_package("app.c..")
            .or_should().depend_on_modules_that().reside_in_a_package("app.a..")
        )
        assert messages(rule, deps_graph) == ["app.d.v imports app.c.w [lazy]"]

    def test_and_should_never_both(self, deps_graph: ImportGraph) -> None:
        rule = (
            no_modules().that().reside_in_a_package("app.d..")
            .should().depend_on_modules_that().reside_in_a_package("app.c..")
            .and_should().depend_on_modules_that().reside_in_a_package("app.a..")
        )
        assert messages(rule, deps_graph) == []

    def test_modules_or_should_passes_when_one_holds(self, deps_graph: ImportGraph) -> None:
        rule = (
            modules().that().reside_in_a_package("app.d.v")
            .should().depend_on_modules_that().reside_in_a_package("app.a..")
            .or_should().depend_on_modules_that().reside_in_a_package("app.b..")
        )
        assert messages(rule, deps_graph) == []

    def test_modules_and_should_reports_failed_part(self, deps_graph: ImportGraph) -> None:
        rule = (
            modules().that().reside_in_a_package("app.d.v")
            .should().depend_on_modules_that().reside_in_a_package("app.b..")
            .and_should().only_depend_on_modules_that().reside_in_a_package("app.b..")
        )
        assert messages(rule, deps_graph) == ["app.d.v imports app.c.w [lazy]"]

    def test_description_reads_as_sentence(self) -> None:
        rule = (
            no_modules().that().reside_in_a_package("a..").and_().reside_outside_of_package("a.b..")
            .should().depend_on_modules_that().reside_in_a_package("c..")
            .or_should().transitively_depend_on_modules_that().have_name_matching("d")
            .because("reason")
        )
        assert rule.description == (
            "no modules that reside in a package 'a..' and reside outside of package 'a.b..' "
            "should depend on modules that reside in a package 'c..' "
            "or should transitively depend on modules that have name matching 'd', because reason"
        )

    def test_as_replaces_description(self) -> None:
        rule = modules().should().depend_on_modules_that().reside_in_a_package("x..").as_("custom").because("why")
        assert rule.description == "custom, because why"


class HasImports(ArchCondition[Module]):
    def __init__(self, limit: int) -> None:
        super().__init__(f"have at most {limit} imports")
        self.limit = limit

    def check(self, item: Module, context: EvaluationContext) -> Iterable[ConditionEvent]:
        count = len(context.imports_of(item.name))
        yield ConditionEvent(item, count <= self.limit, f"{item.name} has {count} imports")


class TestCustomCondition:
    def test_should_with_condition(self, deps_graph: ImportGraph) -> None:
        rule = modules().that().reside_in_a_package("app..").should(HasImports(1))
        assert messages(rule, deps_graph) == ["app.d.v has 2 imports"]

    def test_condition_composition(self, deps_graph: ImportGraph) -> None:
        rule = modules().that().reside_in_a_package("app.d..").should(HasImports(0).or_(HasImports(2)))
        assert messages(rule, deps_graph) == []

    def test_custom_predicate(self, deps_graph: ImportGraph) -> None:
        is_v = DescribedPredicate.describe("are named v", lambda m: m.name.endswith(".v"))
        rule = no_modules().that(is_v).should().depend_on_modules_that().reside_in_a_package("app.b..")
        assert rule.description.startswith("no modules that are named v should")
        assert messages(rule, deps_graph) == ["app.d.v imports app.b.z"]


class TestEmptyAndIgnored:
    def test_empty_selection_is_an_error(self, deps_graph: ImportGraph) -> None:
        rule = modules().that().reside_in_a_package("app.renamed..").should().depend_on_modules_that().reside_in_a_package("x")
        with pytest.raises(EmptyRuleError):
            rule.evaluate(deps_graph)

    def test_empty_selection_allowed_explicitly(self, deps_graph: ImportGraph) -> None:
        rule = (
            modules().that().reside_in_a_package("app.renamed..")
            .should().depend_on_modules_that().reside_in_a_package("x").allow_empty_should(True)
        )
        assert rule.evaluate(deps_graph).passed

    def test_ignore_dependency_hides_edge_and_is_reported(self, deps_graph: ImportGraph) -> None:
        rule = (
            no_modules().that().reside_in_a_package("app.d..")
            .should().depend_on_modules_that().reside_in_a_package("app..")
            .ignore_dependency("app.d.v", "app.c..", reason="legacy")
        )
        result = rule.evaluate(deps_graph)
        assert [v.message for v in result.violations] == ["app.d.v imports app.b.z"]
        assert [(h.edge.imported, h.dependency.reason) for h in result.ignored] == [("app.c.w", "legacy")]

    def test_ignored_edge_is_not_walked_transitively(self, deps_graph: ImportGraph) -> None:
        rule = (
            no_modules().that().reside_in_a_package("app.c..")
            .should().transitively_depend_on_modules_that().have_name_matching("sqlalchemy")
            .ignore_dependency("app.a.y", "app.b..", reason="cut")
        )
        assert messages(rule, deps_graph) == []

    def test_rules_are_immutable(self) -> None:
        base = modules().should().depend_on_modules_that().reside_in_a_package("x..")
        base.because("a")
        assert base.settings.because is None


def test_predicates_compose_descriptions() -> None:
    predicate = reside_in_a_package("a..").and_(not_(have_name_matching("b"))).or_(reside_outside_of_package("c.."))
    assert predicate.description == "reside in a package 'a..' and not have name matching 'b' or reside outside of package 'c..'"
