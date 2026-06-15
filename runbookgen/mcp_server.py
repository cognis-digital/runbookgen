"""RUNBOOKGEN MCP server — exposes runbook generation as an MCP tool."""
from __future__ import annotations

import json
import sys

from runbookgen.core import RunbookError, parse_definition, render_markdown, validate_runbook


def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-runbookgen[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print(
            "Install the MCP extra: pip install 'cognis-runbookgen[mcp]'",
            file=sys.stderr,
        )
        return 1
    app = FastMCP("runbookgen")

    @app.tool()
    def runbookgen_generate(definition: str) -> str:
        """Parse a runbook definition and return JSON with markdown + validation issues."""
        try:
            rb = parse_definition(definition)
        except RunbookError as exc:
            return json.dumps({"error": str(exc)})
        result = rb.to_dict()
        result["markdown"] = render_markdown(rb)
        result["issues"] = validate_runbook(rb)
        return json.dumps(result, indent=2)

    app.run()
    return 0
