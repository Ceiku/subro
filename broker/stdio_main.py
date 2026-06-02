#!/usr/bin/env python3
"""STDIO broker transport: one JSON request per line on stdin, one response per line on stdout."""
from __future__ import annotations

import json
import sys

from handlers import list_tools
from request import BrokerResponse, process_request


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print("subro broker STDIO mode: read JSON lines from stdin, write JSON lines to stdout", file=sys.stderr)
        print(f"tools: {', '.join(list_tools())}", file=sys.stderr)
        sys.exit(0)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as e:
            resp = BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"invalid json: {e}\n")
        else:
            resp = process_request(raw)
        sys.stdout.write(json.dumps(resp.model_dump(), ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
