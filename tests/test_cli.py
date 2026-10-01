from pathlib import Path

import pytest

from archunit.cli import main
from tests.conftest import EXAMPLES, FIXTURES


def run_cli(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    code = main(["check", *args])
    return code, capsys.readouterr().out


def test_example_project_passes(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run_cli(capsys, str(EXAMPLES / "shop"))
    assert code == 0, out
    assert out.rstrip().endswith("17 passed, 0 failed, 0 errors")


def test_violations_errors_and_report(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run_cli(capsys, str(FIXTURES / "cli"))
    assert code == 2  # errors take precedence over violations
    lines = out.splitlines()
    assert "FAIL CoreRules::rule_core_is_pure" in lines
    assert "    proj.core.service imports proj.infra.db (src/proj/core/service.py:1)" in lines
    assert "PASS CoreRules::rule_infra_is_used" in lines
    assert "ERROR Renamed::rule_stale" in lines
    assert any("rule selected no modules" in line for line in lines)
    assert "ERROR Broken::rule_crashes" in lines
    assert any("RuntimeError: boom" in line for line in lines)
    assert not any(line.startswith(("PASS Base", "FAIL Base")) for line in lines)
    assert lines[-1] == "1 passed, 1 failed, 2 errors"


def test_select_filters_rules(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run_cli(capsys, str(FIXTURES / "cli"), "-k", "rule_core")
    assert code == 1
    assert out.rstrip().endswith("0 passed, 1 failed, 0 errors")


def test_missing_config(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["check", str(tmp_path)]) == 2
    assert "pyproject.toml not found" in capsys.readouterr().err


def test_broken_rules_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.archunit]\nroot_packages = ["x"]\n')
    (tmp_path / "arch").mkdir()
    (tmp_path / "arch" / "arch_bad.py").write_text("import does_not_exist\n")
    code, out = run_cli(capsys, str(tmp_path))
    assert code == 2
    assert "ModuleNotFoundError" in out
