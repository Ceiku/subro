#!/usr/bin/env python3
"""Shared Unix-socket client for the agent broker."""
from __future__ import annotations

import json
import os
import socket
import sys
from typing import List


def default_sock() -> str:
    if sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~"),
            "Library",
            "Application Support",
            "agent-broker",
            "agent-broker.sock",
        )
    if sys.platform.startswith("linux"):
        rt = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
        return os.path.join(rt, "agent-broker", "agent-broker.sock")
    return "/tmp/agent-broker/agent-broker.sock"


def call_broker(tool: str, args: List[str], workdir: str | None = None) -> int:
    sock_path = os.environ.get("BROKER_SOCK", default_sock())
    workdir = workdir or os.getcwd()
    req: dict = {"tool": tool, "args": args, "workdir": workdir}
    token = os.environ.get("BROKER_SOCKET_TOKEN", "").strip()
    if token:
        req["token"] = token

    payload = (json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(sock_path)
        s.sendall(payload)
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    finally:
        try:
            s.close()
        except Exception:
            pass

    if not buf:
        print("broker returned no response", file=sys.stderr)
        return 1

    resp = json.loads(buf.decode("utf-8"))
    stdout = resp.get("stdout", "")
    stderr = resp.get("stderr", "")
    code = int(resp.get("exit_code", 1))
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    return code


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: _broker_call.py <tool> [args...]", file=sys.stderr)
        sys.exit(2)
    sys.exit(call_broker(sys.argv[1], sys.argv[2:]))


if __name__ == "__main__":
    main()
