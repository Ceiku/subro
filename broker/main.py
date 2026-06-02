#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError


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
    args: List[str]
    workdir: str = Field(min_length=1)


class BrokerResponse(BaseModel):
    ok: bool
    exit_code: int
    stdout: str
    stderr: str


def _json_dumps_line(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


def _read_allowed_roots() -> List[Path]:
    roots_raw = os.environ.get("BROKER_ALLOWED_ROOTS", "").strip()
    roots: List[Path] = []
    if roots_raw:
        for part in roots_raw.split(","):
            p = part.strip()
            if not p:
                continue
            roots.append(Path(p).expanduser())
    else:
        # Safe-by-default: only allow the broker's current working directory.
        roots.append(Path.cwd())
    return [r.resolve() for r in roots]


@dataclass(frozen=True)
class WorkdirPolicy:
    allowed_roots: List[Path]

    def validate(self, workdir: str) -> Path:
        wd = Path(workdir).expanduser()
        try:
            resolved = wd.resolve(strict=True)
        except FileNotFoundError as e:
            raise ValueError(f"workdir does not exist: {workdir}") from e

        for root in self.allowed_roots:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise ValueError(
            f"workdir not permitted: {resolved} (allowed roots: {', '.join(str(r) for r in self.allowed_roots)})"
        )


def _scrub_secrets(text: str, secrets: List[str]) -> str:
    out = text
    for s in secrets:
        if not s:
            continue
        out = out.replace(s, "[REDACTED]")
    return out


def _run_tool(
    tool: str,
    args: List[str],
    workdir: Path,
    prod_api_key: Optional[str],
) -> Tuple[int, str, str, List[str]]:
    secrets_to_scrub: List[str] = []

    if tool == "mvn":
        cmd = ["mvn", *args]
        # mvn will naturally read ~/.m2/settings.xml based on HOME.
        env = os.environ.copy()
        env.pop("BASH_ENV", None)
        env.pop("ENV", None)
        # Use host HOME; keep execution privileged here (broker side).
        env["HOME"] = str(Path.home())
        # Avoid leaking sensitive env vars to subprocess.
        env.pop("PROD_API_KEY", None)

    elif tool == "curl":
        cmd_args = list(args)
        if prod_api_key and any("X-PROD-KEY" in a for a in cmd_args):
            cmd_args = [a.replace("X-PROD-KEY", prod_api_key) for a in cmd_args]
            secrets_to_scrub.append(prod_api_key)
        cmd = ["/usr/bin/curl", *cmd_args]
        env = os.environ.copy()
        env.pop("PROD_API_KEY", None)
    else:
        raise ValueError(f"unsupported tool: {tool}")

    proc = subprocess.run(
        cmd,
        cwd=str(workdir),
        env=env,
        shell=False,
        capture_output=True,
        text=True,
    )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    return proc.returncode, stdout, stderr, secrets_to_scrub


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    policy = WorkdirPolicy(allowed_roots=_read_allowed_roots())
    prod_api_key = os.environ.get("PROD_API_KEY")

    try:
        line = await reader.readline()
        if not line:
            writer.close()
            await writer.wait_closed()
            return

        try:
            raw = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as e:
            resp = BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"invalid json: {e}\n")
            writer.write(_json_dumps_line(resp.model_dump()))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        try:
            req = BrokerRequest.model_validate(raw)
        except ValidationError as e:
            resp = BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"invalid request: {e}\n")
            writer.write(_json_dumps_line(resp.model_dump()))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        try:
            wd = policy.validate(req.workdir)
        except ValueError as e:
            resp = BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"{e}\n")
            writer.write(_json_dumps_line(resp.model_dump()))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        try:
            code, stdout, stderr, secrets = _run_tool(
                tool=req.tool,
                args=req.args,
                workdir=wd,
                prod_api_key=prod_api_key,
            )
        except Exception as e:
            resp = BrokerResponse(ok=False, exit_code=1, stdout="", stderr=f"broker error: {e}\n")
            writer.write(_json_dumps_line(resp.model_dump()))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        # Always scrub secrets from outputs before returning.
        scrubbed_stdout = _scrub_secrets(stdout, secrets)
        scrubbed_stderr = _scrub_secrets(stderr, secrets)

        resp = BrokerResponse(ok=(code == 0), exit_code=code, stdout=scrubbed_stdout, stderr=scrubbed_stderr)
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

    addrs = ", ".join(str(sock.getsockname()) for sock in (server.sockets or []))
    print(f"broker listening on {addrs}", flush=True)

    async with server:
        await server.serve_forever()


def main() -> None:
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

