"""Core engine for RUNBOOKGEN.

Real logic, standard library only:
  * A small line-based parser for incident/SOP definition files (an INI-ish
    block format that needs no third-party YAML).
  * Severity profiles with response/ack SLAs used to compute a concrete
    escalation timeline.
  * Completeness validation against an SRE runbook checklist.
  * Markdown rendering of a fully structured runbook.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class RunbookError(Exception):
    """Raised for malformed definitions or validation failures."""


class Severity(str, Enum):
    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"

    @classmethod
    def parse(cls, raw: str) -> "Severity":
        key = (raw or "").strip().upper().replace("-", "").replace(" ", "")
        aliases = {
            "SEV1": cls.SEV1, "P1": cls.SEV1, "CRITICAL": cls.SEV1,
            "SEV2": cls.SEV2, "P2": cls.SEV2, "HIGH": cls.SEV2,
            "SEV3": cls.SEV3, "P3": cls.SEV3, "MEDIUM": cls.SEV3,
            "SEV4": cls.SEV4, "P4": cls.SEV4, "LOW": cls.SEV4,
        }
        if key not in aliases:
            raise RunbookError(
                f"unknown severity {raw!r}; use SEV1-4, P1-4, or critical/high/medium/low"
            )
        return aliases[key]


# Each profile: (ack SLA minutes, mitigation target minutes, escalation gap
# minutes, whether an incident commander + comms lead are required).
@dataclass(frozen=True)
class SeverityProfile:
    ack_minutes: int
    mitigate_minutes: int
    escalation_gap_minutes: int
    needs_commander: bool
    needs_comms: bool
    page_on_call: bool


SEVERITY_PROFILES: Dict[Severity, SeverityProfile] = {
    Severity.SEV1: SeverityProfile(5, 30, 15, True, True, True),
    Severity.SEV2: SeverityProfile(15, 120, 30, True, False, True),
    Severity.SEV3: SeverityProfile(60, 480, 120, False, False, False),
    Severity.SEV4: SeverityProfile(240, 2880, 480, False, False, False),
}


@dataclass
class Step:
    order: int
    action: str
    owner: str = "on-call"
    expected: str = ""

    def to_dict(self) -> dict:
        return {
            "order": self.order,
            "action": self.action,
            "owner": self.owner,
            "expected": self.expected,
        }


@dataclass
class Runbook:
    title: str
    severity: Severity
    service: str = ""
    owner_team: str = ""
    summary: str = ""
    symptoms: List[str] = field(default_factory=list)
    detection: List[str] = field(default_factory=list)
    steps: List[Step] = field(default_factory=list)
    rollback: List[str] = field(default_factory=list)
    verification: List[str] = field(default_factory=list)
    escalation: List[str] = field(default_factory=list)
    communication: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)

    @property
    def profile(self) -> SeverityProfile:
        return SEVERITY_PROFILES[self.severity]

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "severity": self.severity.value,
            "service": self.service,
            "owner_team": self.owner_team,
            "summary": self.summary,
            "symptoms": self.symptoms,
            "detection": self.detection,
            "steps": [s.to_dict() for s in self.steps],
            "rollback": self.rollback,
            "verification": self.verification,
            "escalation": self.escalation,
            "communication": self.communication,
            "references": self.references,
            "profile": {
                "ack_minutes": self.profile.ack_minutes,
                "mitigate_minutes": self.profile.mitigate_minutes,
                "escalation_gap_minutes": self.profile.escalation_gap_minutes,
                "needs_commander": self.profile.needs_commander,
                "needs_comms": self.profile.needs_comms,
                "page_on_call": self.profile.page_on_call,
            },
        }


# --- Parsing -----------------------------------------------------------------

_SCALAR_FIELDS = {"title", "severity", "service", "owner_team", "summary"}
_LIST_FIELDS = {
    "symptoms", "detection", "rollback", "verification",
    "escalation", "communication", "references",
}
# steps is a special list-of-records section.


def _split_step(raw: str) -> Step:
    """A step line: 'action | owner=... | expect=...'. Only action required."""
    parts = [p.strip() for p in raw.split("|")]
    action = parts[0]
    owner = "on-call"
    expected = ""
    for extra in parts[1:]:
        if "=" not in extra:
            continue
        k, v = extra.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if k in ("owner", "by"):
            owner = v
        elif k in ("expect", "expected", "verify"):
            expected = v
    return Step(order=0, action=action, owner=owner, expected=expected)


def parse_definition(text: str) -> Runbook:
    """Parse a block-style definition into a Runbook.

    Format (no third-party YAML needed)::

        title: Database connection pool exhausted
        severity: SEV1
        service: orders-api
        symptoms:
          - 5xx spike on /checkout
        steps:
          - Check pool metrics | owner=on-call | expect=usage > 90%
    """
    scalars: Dict[str, str] = {}
    lists: Dict[str, List[str]] = {k: [] for k in _LIST_FIELDS}
    steps: List[Step] = []
    current: Optional[str] = None

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        is_item = stripped.startswith("- ") or stripped == "-"
        if is_item:
            if current is None:
                raise RunbookError(
                    f"line {lineno}: list item with no preceding section header"
                )
            value = stripped[1:].strip()
            if not value:
                continue
            if current == "steps":
                steps.append(_split_step(value))
            elif current in lists:
                lists[current].append(value)
            else:
                raise RunbookError(
                    f"line {lineno}: section {current!r} does not take list items"
                )
            continue

        if ":" not in line:
            raise RunbookError(f"line {lineno}: expected 'key: value' or '- item'")
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()

        if key in _SCALAR_FIELDS:
            scalars[key] = value
            current = None
        elif key in _LIST_FIELDS or key == "steps":
            current = key
            # Allow inline single value: 'symptoms: foo'
            if value:
                if key == "steps":
                    steps.append(_split_step(value))
                else:
                    lists[key].append(value)
        else:
            raise RunbookError(f"line {lineno}: unknown key {key!r}")

    title = scalars.get("title", "").strip()
    if not title:
        raise RunbookError("missing required field: title")
    sev_raw = scalars.get("severity", "").strip()
    if not sev_raw:
        raise RunbookError("missing required field: severity")
    severity = Severity.parse(sev_raw)

    for i, step in enumerate(steps, start=1):
        step.order = i

    return Runbook(
        title=title,
        severity=severity,
        service=scalars.get("service", ""),
        owner_team=scalars.get("owner_team", ""),
        summary=scalars.get("summary", ""),
        symptoms=lists["symptoms"],
        detection=lists["detection"],
        steps=steps,
        rollback=lists["rollback"],
        verification=lists["verification"],
        escalation=lists["escalation"],
        communication=lists["communication"],
        references=lists["references"],
    )


# --- Validation --------------------------------------------------------------

def validate_runbook(rb: Runbook) -> List[str]:
    """Return a list of completeness/quality issues (empty list == ready)."""
    issues: List[str] = []
    if not rb.steps:
        issues.append("no remediation steps defined")
    if not rb.detection:
        issues.append("no detection/alert sources listed")
    if not rb.symptoms:
        issues.append("no symptoms listed (responders can't confirm the match)")
    if not rb.verification:
        issues.append("no verification steps (cannot confirm resolution)")
    if not rb.rollback:
        issues.append("no rollback plan (risky for production changes)")
    if not rb.service:
        issues.append("service not specified")
    if not rb.owner_team:
        issues.append("owner_team not specified (unclear who owns this)")

    prof = rb.profile
    if prof.needs_commander and not rb.escalation:
        issues.append(
            f"{rb.severity.value} requires an incident commander but no "
            "escalation contacts are listed"
        )
    if prof.needs_comms and not rb.communication:
        issues.append(
            f"{rb.severity.value} requires a comms plan but none is listed"
        )
    # Quality: steps should mostly have expected outcomes for SEV1/SEV2.
    if rb.severity in (Severity.SEV1, Severity.SEV2) and rb.steps:
        missing = [s.order for s in rb.steps if not s.expected]
        if missing:
            issues.append(
                "steps missing expected outcomes (high-sev clarity): "
                + ", ".join(f"#{n}" for n in missing)
            )
    return issues


# --- Escalation timeline -----------------------------------------------------

def build_escalation_timeline(
    rb: Runbook, start: Optional[_dt.datetime] = None
) -> List[Tuple[str, str]]:
    """Compute concrete escalation milestones from the severity profile.

    Returns a list of (offset_label, action) tuples. If ``start`` is given,
    offsets are rendered as absolute timestamps; otherwise as +Nm offsets.
    """
    prof = rb.profile

    def label(minutes: int) -> str:
        if start is not None:
            ts = start + _dt.timedelta(minutes=minutes)
            return ts.strftime("%H:%M")
        return f"T+{minutes}m"

    milestones: List[Tuple[int, str]] = [(0, "Incident declared / alert fired")]
    if prof.page_on_call:
        milestones.append((0, "Page primary on-call"))
    milestones.append((prof.ack_minutes, "Ack SLA: responder acknowledges"))
    if prof.needs_commander:
        milestones.append(
            (prof.ack_minutes, "Assign Incident Commander")
        )
    if prof.needs_comms:
        milestones.append(
            (prof.ack_minutes, "Assign Comms Lead; post status page update")
        )
    esc = prof.ack_minutes + prof.escalation_gap_minutes
    milestones.append(
        (esc, "Escalate to secondary on-call / manager if unacknowledged")
    )
    milestones.append(
        (prof.mitigate_minutes, "Mitigation target: service restored or workaround in place")
    )
    milestones.sort(key=lambda m: m[0])
    return [(label(m), action) for m, action in milestones]


# --- Rendering ---------------------------------------------------------------

def _md_list(items: List[str]) -> str:
    return "\n".join(f"- {it}" for it in items) if items else "_None documented._"


def render_markdown(rb: Runbook) -> str:
    prof = rb.profile
    lines: List[str] = []
    lines.append(f"# {rb.title}")
    lines.append("")
    meta = [f"**Severity:** {rb.severity.value}"]
    if rb.service:
        meta.append(f"**Service:** {rb.service}")
    if rb.owner_team:
        meta.append(f"**Owner:** {rb.owner_team}")
    lines.append("  |  ".join(meta))
    lines.append("")
    if rb.summary:
        lines.append(f"> {rb.summary}")
        lines.append("")

    lines.append("## Severity profile")
    lines.append(f"- Ack SLA: {prof.ack_minutes} min")
    lines.append(f"- Mitigation target: {prof.mitigate_minutes} min")
    lines.append(
        f"- Incident commander required: {'yes' if prof.needs_commander else 'no'}"
    )
    lines.append(
        f"- Comms lead required: {'yes' if prof.needs_comms else 'no'}"
    )
    lines.append("")

    lines.append("## Symptoms")
    lines.append(_md_list(rb.symptoms))
    lines.append("")
    lines.append("## Detection")
    lines.append(_md_list(rb.detection))
    lines.append("")

    lines.append("## Escalation timeline")
    for when, action in build_escalation_timeline(rb):
        lines.append(f"- `{when}` {action}")
    lines.append("")

    lines.append("## Remediation steps")
    if rb.steps:
        for s in rb.steps:
            suffix = f" _(owner: {s.owner})_" if s.owner else ""
            lines.append(f"{s.order}. {s.action}{suffix}")
            if s.expected:
                lines.append(f"   - Expected: {s.expected}")
    else:
        lines.append("_None documented._")
    lines.append("")

    lines.append("## Verification")
    lines.append(_md_list(rb.verification))
    lines.append("")
    lines.append("## Rollback")
    lines.append(_md_list(rb.rollback))
    lines.append("")
    lines.append("## Escalation contacts")
    lines.append(_md_list(rb.escalation))
    lines.append("")
    lines.append("## Communication")
    lines.append(_md_list(rb.communication))
    lines.append("")
    lines.append("## References")
    lines.append(_md_list(rb.references))
    lines.append("")
    return "\n".join(lines)
