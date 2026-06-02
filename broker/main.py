#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from audit import audit_event
from handlers import dispatch_scrubbed, list_tools
from policy import WorkdirPolicy, read_allowed_roots


def _default_sock_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "agent-broker" / "agent-broker.sock"
    if sys.platform.startswith("linux"):
        rt = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
        return Path(rt) / "agent-broker" / "agent-broker.sock"
    return Path("/tmp/agent-broker/agent-broker.sock")


SOCK_PATH = Path(os.environ.get("BROKER_SOCK", str(_default_sock_path())))


class BrokerRequest(BaseModel):
    tool: str = Field(min_length=1)
    args: list[str]
    workdir: str = Field(min_length=1)
    token: Optional[str] = None


class BrokerResponse(BaseModel):
    ok: bool
    exit_code: int
    stdout: str
    stderr: str


def _json_dumps_line(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


def _expected_token() -> Optional[str]:
    raw = os.environ.get("BROKER_SOCKET_TOKEN", "").strip()
    return raw or None


def _validate_token(provided: Optional[str]) -> Optional[str]:
    expected = _expected_token()
    if expected is None:
        return None
    if not provided or provided != expected:
        return "unauthorized: invalid or missing broker token"
    return None


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    policy = WorkdirPolicy(allowed_roots=read_allowed_roots())
    prod_api_key = os.environ.get("PROD_API_KEY")

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

        try:
            req = BrokerRequest.model_validate(raw)
        except ValidationError as e:
            resp = BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"invalid request: {e}\n")
            writer.write(_json_dumps_line(resp.model_dump()))
            await writer.drain()
            return

        auth_err = _validate_token(req.token)
        if auth_err:
            resp = BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"{auth_err}\n")
            writer.write(_json_dumps_line(resp.model_dump()))
            await writer.drain()
            audit_event(tool=req.tool, args=req.args, workdir=req.workdir, exit_code=2, ok=False, error=auth_err)
            return

        try:
            wd = policy.validate(req.workdir)
        except ValueError as e:
            resp = BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"{e}\n")
            writer.write(_json_dumps_line(resp.model_dump()))
            await writer.drain()
            audit_event(tool=req.tool, args=req.args, workdir=req.workdir, exit_code=2, ok=False, error=str(e))
            return

        try:
            code, stdout, stderr, ok = dispatch_scrubbed(
                req.tool, req.args, wd, prod_api_key
            )
        except ValueError as e:
            resp = BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"{e}\n")
            writer.write(_json_dumps_line(resp.model_dump()))
            await writer.drain()
            audit_event(tool=req.tool, args=req.args, workdir=str(wd), exit_code=2, ok=False, error=str(e))
            return
        except Exception as e:
            resp = BrokerResponse(ok=False, exit_code=1, stdout="", stderr=f"broker error: {e}\n")
            writer.write(_json_dumps_line(resp.model_dump()))
            await writer.drain()
            audit_event(tool=req.tool, args=req.args, workdir=str(wd), exit_code=1, ok=False, error=str(e))
            return

        audit_event(tool=req.tool, args=req.args, workdir=str(wd), exit_code=code, ok=ok)
        resp = BrokerResponse(ok=ok, exit_code=code, stdout=stdout, stderr=stderr)
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
