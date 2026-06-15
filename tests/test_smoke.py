"""Smoke tests for RUNBOOKGEN. No network. Standard library only."""
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runbookgen import (  # noqa: E402
    TOOL_NAME,
    TOOL_VERSION,
    Severity,
    parse_definition,
    render_markdown,
    validate_runbook,
    build_escalation_timeline,
    RunbookError,
)
from runbookgen.cli import main  # noqa: E402

DEMO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "demos", "01-basic", "pool_exhaustion.runbook",
)

MINIMAL = """\
title: Test incident
severity: SEV3
service: svc
owner_team: team
symptoms:
  - something broke
detection:
  - an alert fired
steps:
  - do the thing | owner=me | expect=it works
verification:
  - confirm fixed
rollback:
  - undo it
"""


class TestMeta(unittest.TestCase):
    def test_tool_identity(self):
        self.assertEqual(TOOL_NAME, "runbookgen")
        self.assertTrue(TOOL_VERSION)


class TestParsing(unittest.TestCase):
    def test_parse_minimal(self):
        rb = parse_definition(MINIMAL)
        self.assertEqual(rb.title, "Test incident")
        self.assertEqual(rb.severity, Severity.SEV3)
        self.assertEqual(len(rb.steps), 1)
        self.assertEqual(rb.steps[0].owner, "me")
        self.assertEqual(rb.steps[0].expected, "it works")
        self.assertEqual(rb.steps[0].order, 1)

    def test_severity_aliases(self):
        self.assertEqual(Severity.parse("p1"), Severity.SEV1)
        self.assertEqual(Severity.parse("critical"), Severity.SEV1)
        self.assertEqual(Severity.parse("LOW"), Severity.SEV4)

    def test_missing_title_raises(self):
        with self.assertRaises(RunbookError):
            parse_definition("severity: SEV1\n")

    def test_unknown_severity_raises(self):
        with self.assertRaises(RunbookError):
            parse_definition("title: x\nseverity: SEV9\n")

    def test_list_item_without_section_raises(self):
        with self.assertRaises(RunbookError):
            parse_definition("- orphan item\n")


class TestValidation(unittest.TestCase):
    def test_minimal_sev3_is_complete(self):
        rb = parse_definition(MINIMAL)
        self.assertEqual(validate_runbook(rb), [])

    def test_sev1_requires_escalation_and_comms(self):
        text = MINIMAL.replace("severity: SEV3", "severity: SEV1")
        rb = parse_definition(text)
        issues = validate_runbook(rb)
        joined = " ".join(issues)
        self.assertIn("escalation", joined)
        self.assertIn("comms", joined)

    def test_demo_validates_clean(self):
        with open(DEMO, encoding="utf-8") as fh:
            rb = parse_definition(fh.read())
        self.assertEqual(rb.severity, Severity.SEV1)
        self.assertEqual(validate_runbook(rb), [])


class TestTimelineAndRender(unittest.TestCase):
    def test_timeline_sev1_pages_and_assigns_ic(self):
        rb = parse_definition(MINIMAL.replace("SEV3", "SEV1"))
        actions = [a for _, a in build_escalation_timeline(rb)]
        self.assertTrue(any("on-call" in a for a in actions))
        self.assertTrue(any("Commander" in a for a in actions))

    def test_render_contains_sections(self):
        rb = parse_definition(MINIMAL)
        md = render_markdown(rb)
        self.assertIn("# Test incident", md)
        self.assertIn("## Remediation steps", md)
        self.assertIn("Expected: it works", md)


class TestCLI(unittest.TestCase):
    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_generate_json(self):
        code, out = self._run(["--format", "json", "generate", DEMO])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["severity"], "SEV1")
        self.assertIn("markdown", data)
        self.assertEqual(data["issues"], [])

    def test_validate_table_ok(self):
        code, out = self._run(["validate", DEMO])
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_validate_fails_nonzero(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
            "w", suffix=".runbook", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("title: bad\nseverity: SEV1\n")
            path = fh.name
        try:
            code, _ = self._run(["validate", path])
            self.assertEqual(code, 2)
        finally:
            os.unlink(path)

    def test_missing_file_returns_one(self):
        code, _ = self._run(["generate", "/no/such/file.runbook"])
        self.assertEqual(code, 1)

    def test_timeline_json(self):
        code, out = self._run(["--format", "json", "timeline", DEMO])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(len(data["timeline"]) >= 4)


class TestHardening(unittest.TestCase):
    """Tests for input validation, error handling, and edge-case paths."""

    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    # --- core: empty step action raises cleanly ----------------------------------

    def test_empty_step_action_raises(self):
        """A step that starts with '|' has no action — should raise RunbookError."""
        text = "title: t\nseverity: SEV3\nsteps:\n  - | owner=me\n"
        with self.assertRaises(RunbookError) as ctx:
            parse_definition(text)
        self.assertIn("empty action", str(ctx.exception))

    # --- core: whitespace-only / comment-only input raises cleanly ---------------

    def test_blank_input_raises_missing_title(self):
        """Empty/whitespace-only definition must raise RunbookError, not AttributeError."""
        for text in ("", "   \n", "# just a comment\n"):
            with self.subTest(text=repr(text)):
                with self.assertRaises(RunbookError) as ctx:
                    parse_definition(text)
                self.assertIn("title", str(ctx.exception))

    # --- core: missing severity raises cleanly -----------------------------------

    def test_missing_severity_raises(self):
        with self.assertRaises(RunbookError) as ctx:
            parse_definition("title: x\n")
        self.assertIn("severity", str(ctx.exception))

    # --- CLI: missing file returns exit code 1 with message to stderr ------------

    def test_missing_file_stderr_message(self):
        import io as _io
        stderr_buf = _io.StringIO()
        with redirect_stdout(_io.StringIO()):
            old_err, sys.stderr = sys.stderr, stderr_buf
            try:
                code = main(["generate", "/no/such/path/file.runbook"])
            finally:
                sys.stderr = old_err
        self.assertEqual(code, 1)
        self.assertIn("file not found", stderr_buf.getvalue())

    # --- CLI: binary/non-UTF-8 file returns exit code 1 -------------------------

    def test_binary_file_returns_one(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".runbook") as fh:
            fh.write(b"\xff\xfe binary garbage \x00\x01\x02")
            path = fh.name
        try:
            code, _ = self._run(["generate", path])
            self.assertEqual(code, 1)
        finally:
            os.unlink(path)

    # --- mcp_server: module imports cleanly with correct API ---------------------

    def test_mcp_server_imports(self):
        """mcp_server must import without ImportError (the broken scan/to_json refs are fixed)."""
        import runbookgen.mcp_server as mod
        self.assertTrue(callable(mod.serve))

    # --- webhook: URL validation -------------------------------------------------

    def test_webhook_rejects_bad_url(self):
        """webhook.main() must reject non-http(s) URLs with exit code 2."""
        import sys as _sys
        import io as _io
        from integrations.webhook import main as wh_main

        old_argv, _sys.argv = _sys.argv, ["webhook.py", "--url", "ftp://example.com"]
        old_stdin, _sys.stdin = _sys.stdin, _io.TextIOWrapper(_io.BytesIO(b"{}"))
        stderr_buf = _io.StringIO()
        old_err, _sys.stderr = _sys.stderr, stderr_buf
        try:
            code = wh_main()
        finally:
            _sys.argv = old_argv
            _sys.stdin = old_stdin
            _sys.stderr = old_err
        self.assertEqual(code, 2)
        self.assertIn("http", stderr_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
