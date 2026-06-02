#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from handlers import list_tools
from request import BrokerResponse, process_request


def _default_sock_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "agent-broker" / "agent-broker.sock"
    if sys.platform.startswith("linux"):
        rt = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
        return Path(rt) / "agent-broker" / "agent-broker.sock"
    return Path("/tmp/agent-broker/agent-broker.sock")


SOCK_PATH = Path(os.environ.get("BROKER_SOCK", str(_default_sock_path())))


def _json_dumps_line(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        line = await reader.readline()
        if not line:
            return

        try:
            raw = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as e:
            resp = BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"invalid json: {e}\n")
            writer.write(_json_dumps_line(resp.model_dump()))
            await writer.drain()
            return

        resp = process_request(raw)
        writer.write(_json_dumps_line(resp.model_dump()))
        await writer.drain()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def run_server() -> None:
    SOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SOCK_PATH.exists():
        try:
            SOCK_PATH.unlink()
        except Exception as e:
            print(f"failed to remove existing socket: {SOCK_PATH}: {e}", file=sys.stderr)
            sys.exit(1)

    server = await asyncio.start_unix_server(handle_client, path=str(SOCK_PATH))
    os.chmod(SOCK_PATH, 0o600)

    tools = ", ".join(list_tools())
    print(f"broker listening on {SOCK_PATH} (tools: {tools})", flush=True)

    async with server:
        await server.serve_forever()


def main() -> None:
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
