"""Stage 1: import rules between modules, using a sample ``shop`` project.

Project layout::

    shop/
      __main__.py, main.py, di.py       # entrypoint and composition root
      api/  workers/  migrations/
      settings/  shared/
      features/
        generic/  (users, files, audit)
        support/  (notifications, search)
        core/     (catalog, orders, billing, payments)
    libs/
      http/                              # base HTTP client
      payments_client/                   # external payment service client built on http

``pyproject.toml``::

    [tool.archunit]
    root_packages = ["shop", "libs"]
"""

from collections.abc import Iterable

from archunit import (
    AnalyzeModules,
    ArchCondition,
    ArchRule,
    ArchSuite,
    ConditionEvent,
    EvaluationContext,
    Module,
    modules,
    no_modules,
)
from archunit.predicates import (
    have_name_matching,
    not_,
    reside_in_a_package,
    reside_in_any_package,
    reside_outside_of_packages,
)

SETTINGS = "shop.settings.."
SHARED = "shop.shared.."


class TopLevelPackages(ArchSuite):
    """Top level: each package imports only what is allowed from the project.

    ``only_depend_on_modules_that`` is strict, as in Java: stdlib and third-party packages are checked too.
    Everything outside the project is allowed explicitly with ``.or_(reside_outside_of_packages("shop..", "libs.."))``.
    """

    def rule_api(self) -> ArchRule:
        return self._layer("shop.api..", "shop.api..", "shop.features..", SHARED, SETTINGS, "shop.di")

    def rule_features(self) -> ArchRule:
        return self._layer("shop.features..", "shop.features..", SHARED, SETTINGS)

    def rule_shared(self) -> ArchRule:
        return self._layer(SHARED, SHARED, SETTINGS)

    def rule_settings(self) -> ArchRule:
        return self._layer(SETTINGS, SETTINGS)

    def rule_workers(self) -> ArchRule:
        return self._layer("shop.workers..", "shop.workers..", "shop.features..", SHARED, SETTINGS, "shop.di")

    def rule_dunder_main(self) -> ArchRule:
        # __main__ is a thin entrypoint: it prepares the environment and hands over to shop.main.
        return self._layer("shop.__main__", "shop.main")

    def _layer(self, layer: str, *allowed: str) -> ArchRule:
        return (
            modules().that().reside_in_a_package(layer)
            .should().only_depend_on_modules_that(
                reside_in_any_package(*allowed, "libs..").or_(reside_outside_of_packages("shop..", "libs.."))
            )
        )


class FeatureTiers(ArchSuite):
    """generic <- support <- core: a lower tier knows nothing about upper ones."""

    because = "upper-tier contexts are built on top of lower ones, not the other way round"
    tiers = ("generic", "support", "core")

    def rule_generic(self) -> ArchRule:
        return self._tier("generic")

    def rule_support(self) -> ArchRule:
        return self._tier("support")

    def _tier(self, tier: str) -> ArchRule:
        upper = self.tiers[self.tiers.index(tier) + 1 :]
        return (
            no_modules().that().reside_in_a_package(f"shop.features.{tier}..")
            .should().depend_on_modules_that().reside_in_any_package(*(f"shop.features.{t}.." for t in upper))
        )


class CoreContexts(ArchSuite):
    """Order inside core: payments <- billing <- orders; catalog depends on nothing."""

    core = "shop.features.core"

    def rule_catalog_is_independent(self) -> ArchRule:
        return self._context("catalog")

    def rule_billing(self) -> ArchRule:
        return self._context("billing", "payments")

    def rule_orders(self) -> ArchRule:
        return self._context("orders", "billing", "catalog").ignore_dependency(
            "shop.features.core.orders.legacy..",
            "shop.features.core.payments..",
            reason="legacy checkout, being removed as part of the move to billing",
        )

    def _context(self, name: str, *allowed: str) -> ArchRule:
        """Inside core a context imports only itself and the listed contexts; nothing outside core is restricted.

        Java: ``noClasses().that()...should().dependOnClassesThat(resideInAPackage(core).and(not(...)))``.
        """
        own_and_allowed = (f"{self.core}.{ctx}.." for ctx in (name, *allowed))
        return (
            no_modules().that().reside_in_a_package(f"{self.core}.{name}..")
            .should().depend_on_modules_that(
                reside_in_a_package(f"{self.core}..").and_(not_(reside_in_any_package(*own_and_allowed)))
            )
        )


class TransportBoundary(ArchSuite):
    """Transport lives in libs and never looks up; the payment service client is visible only to the gateway."""

    analyze = AnalyzeModules("shop", "libs")
    gateway = "shop.features.core.payments.gateway"

    def rule_libs_do_not_know_the_app(self) -> ArchRule:
        return (
            no_modules().that().reside_in_a_package("libs..")
            .should().transitively_depend_on_modules_that().reside_in_a_package("shop..")
            .because("a library that knows the domain is no longer a library")
        )

    def rule_transport_core_does_not_know_the_service(self) -> ArchRule:
        return (
            no_modules().that().reside_in_a_package("libs.http..")
            .should().depend_on_modules_that().reside_in_a_package("libs.payments_client..")
            .or_should().transitively_depend_on_modules_that().reside_in_a_package("shop..")
        )

    def rule_service_client_is_private_to_the_gateway(self) -> ArchRule:
        return (
            modules().that().reside_in_a_package("libs.payments_client..")
            .should().only_be_accessed().by_modules_that().reside_in_any_package(f"{self.gateway}..", "shop.di")
            .because("the external service name must not leak past the gateway")
        )


class BillingBoundaries(ArchSuite):
    """Composition of selections, predicates and conditions."""

    billing = "shop.features.core.billing"

    def rule_domain_is_pure(self) -> ArchRule:
        return (
            no_modules().that().reside_in_a_package(f"{self.billing}.domain..")
            .should().depend_on_modules_that().reside_in_any_package("libs..", f"{self.billing}.gateways..")
            .or_should().depend_on_modules_that().have_name_matching(r"sqlalchemy(\..*)?")
        )

    def rule_events_are_the_only_public_entry(self) -> ArchRule:
        # Outside billing only events are accessible; billing itself and the composition root are unrestricted.
        return (
            modules().that().reside_in_a_package(f"{self.billing}..")
            .and_(not_(have_name_matching(rf"{self.billing}\.events(\..*)?")))
            .should().only_be_accessed().by_modules_that(
                reside_in_a_package(f"{self.billing}..").or_(reside_in_a_package("shop.di"))
            )
        )

    def rule_use_cases_are_thin(self) -> ArchRule:
        return (
            modules().that().reside_in_a_package(f"{self.billing}.use_cases..")
            .should().only_depend_on_modules_that().reside_in_any_package(
                f"{self.billing}..", SHARED, "shop.features.core.payments..", "typing", "dataclasses", "decimal"
            )
            .and_should(HaveAtMostImports(15))
        )


class HaveAtMostImports(ArchCondition[Module]):
    """A custom condition (Java: an ``ArchCondition`` subclass)."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"have at most {limit} imports")
        self.limit = limit

    def check(self, item: Module, context: EvaluationContext) -> Iterable[ConditionEvent]:
        count = len(context.graph.imports_of(item.name))
        yield ConditionEvent(item, count <= self.limit, f"{item.name} has {count} imports")


class AllImportRules(ArchSuite):
    """Suite composition (Java: ``ArchTests.in``): a single entry-point suite for a CI job."""

    include = (TopLevelPackages, FeatureTiers, CoreContexts, TransportBoundary, BillingBoundaries)
