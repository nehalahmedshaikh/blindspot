from __future__ import annotations

import argparse
import sys

from .pipeline import analyze, build, export, refresh, validate
from .sources import SourceError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="blindspot", description="Global measurement-gap observatory")
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("fetch", help="Refresh official source data")
    build_parser = subcommands.add_parser("build", help="Calculate descriptive metrics and rankings")
    build_parser.add_argument("--completed-year", type=int, default=None)
    subcommands.add_parser("analyze", help="Analyze inequalities and robustness")
    subcommands.add_parser("validate", help="Validate configuration and generated metrics")
    subcommands.add_parser("export", help="Create static-site datasets and downloads")
    subcommands.add_parser("all", help="Run the complete research and export pipeline")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "fetch":
            fresh = refresh()
            print("Source refresh complete." if fresh else "Refresh failed; retained the previous validated snapshot unchanged.")
        elif args.command == "build":
            result = build(args.completed_year)
            print(f"Built {len(result['country_series']):,} country-series assessments.")
        elif args.command == "analyze":
            result = analyze()
            design = result["design"]
            print(
                f"Analyzed {design['countries']} countries across "
                f"{design['universal_series']} universal series."
            )
        elif args.command == "validate":
            for check in validate():
                print(f"✓ {check}")
        elif args.command == "export":
            result = export()
            print(f"Exported partitioned site data for {len(result['countries'])} countries.")
        elif args.command == "all":
            if not refresh():
                raise SourceError("Source refresh failed; retained the previous validated snapshot")
            build()
            analyze()
            for check in validate():
                print(f"✓ {check}")
            export()
        return 0
    except (SourceError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
