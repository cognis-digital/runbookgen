"""RUNBOOKGEN MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from runbookgen.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-runbookgen[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-runbookgen[mcp]'")
        return 1
    app = FastMCP("runbookgen")

    @app.tool()
    def runbookgen_scan(target: str) -> str:
        """Incident runbook and SOP generator from templates. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
