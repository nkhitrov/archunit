import pytest

from archunit import AnalyzeModules, ArchRule, ArchSuite, modules


def rule(pattern: str) -> ArchRule:
    return modules().that().reside_in_a_package(pattern).should().depend_on_modules_that().reside_in_a_package("x..")


class Parent(ArchSuite):
    because = "parent reason"
    target = "p"

    def rule_b(self) -> ArchRule:
        return rule(self.target)

    def rule_a(self) -> ArchRule:
        return rule("a").because("own reason")

    def _helper(self) -> ArchRule:
        return rule("helper")

    def not_a_rule(self) -> ArchRule:
        return rule("no")


class Child(Parent):
    target = "c"

    def rule_c(self) -> ArchRule:
        return self._helper()


class Shared(ArchSuite):
    analyze = AnalyzeModules("shared_pkg")

    def rule_shared(self) -> ArchRule:
        return rule("s")


class Root(ArchSuite):
    analyze = AnalyzeModules("root_pkg")
    include = (Child, Shared, Child)

    def rule_root(self) -> ArchRule:
        return rule("r")


def test_rule_names_follow_declaration_order_and_inheritance() -> None:
    assert Child.rule_names() == ["rule_b", "rule_a", "rule_c"]


def test_rules_use_self_and_suite_defaults() -> None:
    rules = {r.rule_id: r.build() for r in Child().rules()}
    assert list(rules) == ["Child::rule_b", "Child::rule_a", "Child::rule_c"]
    assert rules["Child::rule_b"].description.startswith("modules that reside in a package 'c'")
    assert rules["Child::rule_b"].settings.because == "parent reason"
    assert rules["Child::rule_a"].settings.because == "own reason"


def test_include_runs_once_and_inherits_analyze() -> None:
    collected = [(r.rule_id, r.analyze) for r in Root().rules()]
    assert [rule_id for rule_id, _ in collected] == [
        "Root::rule_root",
        "Child::rule_b",
        "Child::rule_a",
        "Child::rule_c",
        "Shared::rule_shared",
    ]
    analyzed = {rule_id: analyze.packages for rule_id, analyze in collected if analyze}
    assert analyzed["Child::rule_c"] == ("root_pkg",)
    assert analyzed["Shared::rule_shared"] == ("shared_pkg",)


def test_rule_method_must_return_rule() -> None:
    class Bad(ArchSuite):
        def rule_x(self) -> object:
            return "nope"

    (suite_rule,) = Bad().rules()
    with pytest.raises(TypeError, match="Bad::rule_x must return ArchRule"):
        suite_rule.build()
