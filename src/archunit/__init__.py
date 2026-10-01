"""archunit — architecture rules for Python projects, inspired by Java ArchUnit."""

from archunit.core.graph import ImportGraph
from archunit.core.model import Import, Module
from archunit.lang.modules import modules, no_modules
from archunit.lang.conditions import ArchCondition, ConditionEvent, EvaluationContext
from archunit.lang.predicates import DescribedPredicate
from archunit.lang.rule import ArchRule, EmptyRuleError, EvaluationResult, Violation
from archunit.suite import AnalyzeModules, ArchSuite

__version__ = "0.0.1"

__all__ = [
    "AnalyzeModules",
    "ArchCondition",
    "ArchRule",
    "ArchSuite",
    "ConditionEvent",
    "DescribedPredicate",
    "EmptyRuleError",
    "EvaluationContext",
    "EvaluationResult",
    "Import",
    "ImportGraph",
    "Module",
    "Violation",
    "modules",
    "no_modules",
]
