"""Plain-text report for terminals and CI logs."""

from __future__ import annotations

from pathlib import Path

from archunit.runner import Report, RuleOutcome


def format_report(report: Report, project_dir: Path) -> str:
    lines: list[str] = [f"ERROR loading rules\n{error}" for error in report.errors]
    for outcome in report.outcomes:
        lines.extend(_format_outcome(outcome, project_dir))
    lines.append(_summary(report))
    return "\n".join(lines)


def _format_outcome(outcome: RuleOutcome, project_dir: Path) -> list[str]:
    if outcome.error is not None:
        header = [f"ERROR {outcome.rule_id}"] + ([f"  {outcome.description}"] if outcome.description else [])
        return [*header, _indent(outcome.error.rstrip())]
    assert outcome.result is not None
    result = outcome.result
    status = "PASS" if result.passed else "FAIL"
    lines = [f"{status} {outcome.rule_id}"]
    if not result.passed:
        lines.append(f"  Rule '{result.rule_description}' was violated ({len(result.violations)} times):")
        for violation in result.violations:
            location = _location(violation.path, violation.line, project_dir)
            lines.append(f"    {violation.message}" + (f" ({location})" if location else ""))
    for hit in result.ignored:
        lines.append(f"  ignored: {hit.edge.importer} imports {hit.edge.imported} — {hit.dependency.reason}")
    return lines


def _location(path: Path | None, line: int | None, project_dir: Path) -> str:
    if path is None:
        return ""
    try:
        shown = path.resolve().relative_to(project_dir.resolve())
    except ValueError:
        shown = path
    return f"{shown}:{line}" if line is not None else str(shown)


def _summary(report: Report) -> str:
    passed = sum(1 for o in report.outcomes if o.result is not None and o.result.passed)
    failed = sum(1 for o in report.outcomes if o.result is not None and not o.result.passed)
    errors = sum(1 for o in report.outcomes if o.error is not None) + len(report.errors)
    return f"\n{passed} passed, {failed} failed, {errors} errors"


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())
