"""``archunit check [PROJECT_DIR] [-k SUBSTRING]`` — exit 0 / 1 (violations) / 2 (errors)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from archunit.runner import ArchunitConfig, ConfigError, run
from archunit.runner.text_report import format_report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="archunit")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check the architecture rules of a project")
    check.add_argument("project_dir", nargs="?", default=".", type=Path)
    check.add_argument("-k", dest="select", help="only rules whose id contains the substring")
    args = parser.parse_args(argv)

    try:
        config = ArchunitConfig.load(args.project_dir)
    except ConfigError as error:
        print(f"archunit: {error}", file=sys.stderr)
        return 2
    report = run(config, select=args.select)
    print(format_report(report, config.project_dir))
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
