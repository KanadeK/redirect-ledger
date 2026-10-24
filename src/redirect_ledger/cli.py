"""Command-line interface with stable exit status and machine-readable errors."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .core import InputError, audit, parse_inventory, parse_rules, plan_csv, read_text, write_new


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit a local exact-path redirect CSV; never fetch URLs."
    )
    parser.add_argument("map", help="UTF-8 CSV: source,target,status")
    parser.add_argument("--inventory", help="UTF-8 text with one live root-relative path per line")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument(
        "--strict", action="store_true", help="return 1 for chain warnings as well as errors"
    )
    parser.add_argument("--plan", help="write a complete conservative CSV plan to a NEW file")
    parser.add_argument("--version", action="version", version=f"redirect-ledger {__version__}")
    args = parser.parse_args(argv)
    try:
        rules = parse_rules(read_text(args.map))
        inventory = parse_inventory(read_text(args.inventory)) if args.inventory else None
        report = audit(rules, inventory)
        if args.plan:
            write_new(args.plan, plan_csv(report))
    except (InputError, OSError) as exc:
        # File paths may be private; do not copy OS error text to CI output.
        message = (
            str(exc)
            if isinstance(exc, InputError)
            else "file access failed (missing, existing output, or permissions)"
        )
        error = {"schema_version": 1, "error": message}
        print(
            json.dumps(error) if args.format == "json" else f"redirect-ledger: {message}",
            file=sys.stderr,
        )
        return 2
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        summary = report["summary"]
        print(
            f"redirect-ledger: {summary['rules']} rules, {summary['errors']} errors, {summary['warnings']} warnings"
        )
        for finding in report["findings"]:
            print(f"{finding['severity']}: {finding['code']} {json.dumps(finding['source'])}")
        if not report["inventory_checked"]:
            print("Internal terminal existence unchecked: supply --inventory.")
    return int(bool(report["summary"]["errors"] or (args.strict and report["summary"]["warnings"])))
