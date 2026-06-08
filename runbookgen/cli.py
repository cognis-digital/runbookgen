"""Command-line interface for RUNBOOKGEN.

Subcommands:
  generate  Parse a definition and emit a Markdown runbook (or JSON).
  validate  Check a definition for completeness against the SRE checklist.
  timeline  Print the computed escalation timeline.

Global: --version, --format {table,json}.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from runbookgen import TOOL_NAME, TOOL_VERSION
from runbookgen.core import (
    RunbookError,
    build_escalation_timeline,
    parse_definition,
    render_markdown,
    validate_runbook,
)


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _cmd_generate(args: argparse.Namespace) -> int:
    rb = parse_definition(_read(args.input))
    if args.format == "json":
        out = dict(rb.to_dict())
        out["markdown"] = render_markdown(rb)
        out["issues"] = validate_runbook(rb)
        print(json.dumps(out, indent=2))
    else:
        print(render_markdown(rb))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    rb = parse_definition(_read(args.input))
    issues = validate_runbook(rb)
    if args.format == "json":
        print(json.dumps(
            {"title": rb.title, "severity": rb.severity.value,
             "ok": not issues, "issues": issues},
            indent=2,
        ))
    else:
        if not issues:
            print(f"OK: '{rb.title}' is complete ({rb.severity.value}).")
        else:
            print(f"FAIL: '{rb.title}' has {len(issues)} issue(s):")
            for i in issues:
                print(f"  - {i}")
    return 0 if not issues else 2


def _cmd_timeline(args: argparse.Namespace) -> int:
    rb = parse_definition(_read(args.input))
    timeline = build_escalation_timeline(rb)
    if args.format == "json":
        print(json.dumps(
            {"title": rb.title, "severity": rb.severity.value,
             "timeline": [{"when": w, "action": a} for w, a in timeline]},
            indent=2,
        ))
    else:
        print(f"Escalation timeline for '{rb.title}' ({rb.severity.value}):")
        for when, action in timeline:
            print(f"  {when:>8}  {action}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Incident runbook and SOP generator from templates.",
    )
    p.add_argument(
        "--version", action="version",
        version=f"{TOOL_NAME} {TOOL_VERSION}",
    )
    p.add_argument(
        "--format", choices=["table", "json"], default="table",
        help="output format (default: table)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="render a runbook from a definition")
    g.add_argument("input", help="definition file path, or '-' for stdin")
    g.set_defaults(func=_cmd_generate)

    v = sub.add_parser("validate", help="check a definition for completeness")
    v.add_argument("input", help="definition file path, or '-' for stdin")
    v.set_defaults(func=_cmd_validate)

    t = sub.add_parser("timeline", help="print the escalation timeline")
    t.add_argument("input", help="definition file path, or '-' for stdin")
    t.set_defaults(func=_cmd_timeline)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RunbookError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc.filename}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
