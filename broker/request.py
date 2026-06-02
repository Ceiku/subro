"""Shared broker request processing (UDS + STDIO)."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

from audit import audit_event
from handlers import dispatch_scrubbed, invalidate_registry, list_tools
from policy import WorkdirPolicy, read_allowed_roots
from register import RegisterSkillSpec, register_skill


class BrokerRequest(BaseModel):
    tool: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    workdir: str = Field(min_length=1)
    token: Optional[str] = None
    register_skill: Optional[RegisterSkillSpec] = None


class BrokerResponse(BaseModel):
    ok: bool
    exit_code: int
    stdout: str
    stderr: str


def expected_token() -> Optional[str]:
    raw = os.environ.get("BROKER_SOCKET_TOKEN", "").strip()
    return raw or None


def validate_token(provided: Optional[str]) -> Optional[str]:
    expected = expected_token()
    if expected is None:
        return None
    if not provided or provided != expected:
        return "unauthorized: invalid or missing broker token"
    return None


def process_request(raw: Dict[str, Any]) -> BrokerResponse:
    try:
        req = BrokerRequest.model_validate(raw)
    except ValidationError as e:
        return BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"invalid request: {e}\n")

    auth_err = validate_token(req.token)
    if auth_err:
        audit_event(tool=req.tool, args=req.args, workdir=req.workdir, exit_code=2, ok=False, error=auth_err)
        return BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"{auth_err}\n")

    policy = WorkdirPolicy(allowed_roots=read_allowed_roots())
    try:
        wd = policy.validate(req.workdir)
    except ValueError as e:
        audit_event(tool=req.tool, args=req.args, workdir=req.workdir, exit_code=2, ok=False, error=str(e))
        return BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"{e}\n")

    prod_api_key = os.environ.get("PROD_API_KEY")

    if req.tool == "register-skill":
        if req.register_skill is None:
            return BrokerResponse(
                ok=False,
                exit_code=2,
                stdout="",
                stderr="register_skill payload required\n",
            )
        code, stdout, stderr = register_skill(req.register_skill, wd)
        if code == 0:
            invalidate_registry()
        audit_event(tool=req.tool, args=req.args, workdir=str(wd), exit_code=code, ok=(code == 0))
        return BrokerResponse(ok=(code == 0), exit_code=code, stdout=stdout, stderr=stderr)

    if req.tool == "list-tools":
        tools = list_tools()
        import json as _json

        return BrokerResponse(
            ok=True,
            exit_code=0,
            stdout=_json.dumps({"tools": tools}, indent=2) + "\n",
            stderr="",
        )

    try:
        code, stdout, stderr, ok = dispatch_scrubbed(req.tool, req.args, wd, prod_api_key)
    except ValueError as e:
        audit_event(tool=req.tool, args=req.args, workdir=str(wd), exit_code=2, ok=False, error=str(e))
        return BrokerResponse(ok=False, exit_code=2, stdout="", stderr=f"{e}\n")
    except Exception as e:
        audit_event(tool=req.tool, args=req.args, workdir=str(wd), exit_code=1, ok=False, error=str(e))
        return BrokerResponse(ok=False, exit_code=1, stdout="", stderr=f"broker error: {e}\n")

    audit_event(tool=req.tool, args=req.args, workdir=str(wd), exit_code=code, ok=ok)
    return BrokerResponse(ok=ok, exit_code=code, stdout=stdout, stderr=stderr)
