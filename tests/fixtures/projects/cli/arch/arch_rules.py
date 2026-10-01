from archunit import ArchRule, ArchSuite, modules, no_modules


class Base(ArchSuite):
    """A helper suite without rules — never runs on its own."""

    core = "proj.core.."


class CoreRules(Base):
    because = "the core knows nothing about infrastructure"

    def rule_core_is_pure(self) -> ArchRule:
        return no_modules().that().reside_in_a_package(self.core).should().depend_on_modules_that().reside_in_a_package("proj.infra..")

    def rule_infra_is_used(self) -> ArchRule:
        return modules().that().reside_in_a_package("proj.infra..").should().only_be_accessed().by_modules_that().reside_in_a_package("proj..")


class Renamed(ArchSuite):
    def rule_stale(self) -> ArchRule:
        return modules().that().reside_in_a_package("proj.old..").should().depend_on_modules_that().reside_in_a_package("x")


class Broken(ArchSuite):
    def rule_crashes(self) -> ArchRule:
        raise RuntimeError("boom")
