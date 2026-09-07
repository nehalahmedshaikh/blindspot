from __future__ import annotations

import argparse
import json
import sys

from .pipeline import build, export, model, refresh, validate
from .sources import SourceError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="blindspot", description="Global measurement-gap observatory")
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("fetch", help="Refresh official source data")
    build_parser = subcommands.add_parser("build", help="Calculate descriptive metrics and rankings")
    build_parser.add_argument("--completed-year", type=int, default=None)
    subcommands.add_parser("model", help="Backtest the reporting-continuity model")
    subcommands.add_parser("validate", help="Validate configuration and generated metrics")
    subcommands.add_parser("export", help="Create static-site datasets and downloads")
    subcommands.add_parser("all", help="Run fetch, build, model, validate, and export")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "fetch":
            fresh = refresh()
            print("Source refresh complete." if fresh else "Refresh failed; retained and marked the prior snapshot stale.")
        elif args.command == "build":
            result = build(args.completed_year)
            print(f"Built {len(result['country_series']):,} country-series assessments.")
        elif args.command == "model":
            result = model()
            print(json.dumps({"selected": result["selected"], "candidates": result["candidates"]}, indent=2))
        elif args.command == "validate":
            for check in validate():
                print(f"✓ {check}")
        elif args.command == "export":
            result = export()
            print(f"Exported dashboard for {len(result['countries'])} countries.")
        elif args.command == "all":
            refresh()
            build()
            model()
            for check in validate():
                print(f"✓ {check}")
            export()
        return 0
    except (SourceError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
