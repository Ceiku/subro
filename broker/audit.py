"""Append-only audit log for broker tool invocations."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _audit_path() -> Optional[Path]:
    raw = os.environ.get("BROKER_AUDIT_LOG", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".config" / "agent-broker" / "audit.jsonl"


def audit_event(
    *,
    tool: str,
    args: List[str],
    workdir: str,
    exit_code: int,
    ok: bool,
    error: Optional[str] = None,
) -> None:
    path = _audit_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    event: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "args": args,
        "workdir": workdir,
        "exit_code": exit_code,
        "ok": ok,
    }
    if error:
        event["error"] = error
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
