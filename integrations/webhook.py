#!/usr/bin/env python3
"""Minimal, dependency-free webhook forwarder for runbookgen findings.

Reads JSON findings on stdin and POSTs them to a URL (SIEM/Slack/Jira bridge).
Usage:  runbookgen --format json generate FILE | python integrations/webhook.py --url URL
"""
from __future__ import annotations

import argparse
import sys
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser(
        description="POST runbookgen JSON output to a webhook URL.",
    )
    ap.add_argument("--url", required=True, help="Destination URL (http/https)")
    ap.add_argument("--header", action="append", default=[], help="Extra header as 'Key: Value'")
    args = ap.parse_args()

    if not args.url.startswith(("http://", "https://")):
        print(
            f"error: --url must start with http:// or https://; got {args.url!r}",
            file=sys.stderr,
        )
        return 2

    try:
        payload = sys.stdin.buffer.read()
    except Exception as exc:  # noqa: BLE001
        print(f"error: failed to read stdin: {exc}", file=sys.stderr)
        return 1

    if not payload:
        print("error: stdin is empty; nothing to post", file=sys.stderr)
        return 2

    req = urllib.request.Request(args.url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    for h in args.header:
        k, _, v = h.partition(":")
        if not k.strip():
            print(f"error: malformed --header value {h!r}; expected 'Key: Value'", file=sys.stderr)
            return 2
        req.add_header(k.strip(), v.strip())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"posted {len(payload)} bytes -> {r.status}")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"webhook error: HTTP {exc.code} {exc.reason}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"webhook error: {exc.reason}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"webhook error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
