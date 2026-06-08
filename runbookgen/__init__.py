"""RUNBOOKGEN - Incident runbook and SOP generator from templates.

Generate consistent, complete incident runbooks and standard operating
procedures from compact definitions. In the spirit of Tettra-style ops/SRE
knowledge management: turn tribal knowledge into structured, validated docs.
"""
from runbookgen.core import (
    Runbook,
    Step,
    Severity,
    parse_definition,
    render_markdown,
    validate_runbook,
    build_escalation_timeline,
    SEVERITY_PROFILES,
    RunbookError,
)

TOOL_NAME = "runbookgen"
TOOL_VERSION = "1.0.0"

__all__ = [
    "Runbook",
    "Step",
    "Severity",
    "parse_definition",
    "render_markdown",
    "validate_runbook",
    "build_escalation_timeline",
    "SEVERITY_PROFILES",
    "RunbookError",
    "TOOL_NAME",
    "TOOL_VERSION",
]
