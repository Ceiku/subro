#!/usr/bin/env python3
"""Tool registry and dispatch for the agent broker."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from policy import scrub_secrets

# (args, workdir, prod_api_key) -> (exit_code, stdout, stderr, secrets_to_scrub)
Handler = Callable[..., Tuple[int, str, str, List[str]]]

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def _run_mvn(args: List[str], workdir: Path, prod_api_key: Optional[str]) -> Tuple[int, str, str, List[str]]:
    env = os.environ.copy()
    env.pop("BASH_ENV", None)
    env.pop("ENV", None)
    env["HOME"] = str(Path.home())
    env.pop("PROD_API_KEY", None)
    proc = subprocess.run(
        ["mvn", *args],
        cwd=str(workdir),
        env=env,
        shell=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or "", []


def _run_curl(args: List[str], workdir: Path, prod_api_key: Optional[str]) -> Tuple[int, str, str, List[str]]:
    secrets: List[str] = []
    cmd_args = list(args)
    if prod_api_key and any("X-PROD-KEY" in a for a in cmd_args):
        cmd_args = [a.replace("X-PROD-KEY", prod_api_key) for a in cmd_args]
        secrets.append(prod_api_key)
    env = os.environ.copy()
    env.pop("PROD_API_KEY", None)
    proc = subprocess.run(
        ["/usr/bin/curl", *cmd_args],
        cwd=str(workdir),
        env=env,
        shell=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or "", secrets


def _wrap_skill_run(
    run_fn: Callable[[List[str]], Tuple[int, str, str, List[str]]],
) -> Handler:
    def _handler(args: List[str], workdir: Path, prod_api_key: Optional[str]) -> Tuple[int, str, str, List[str]]:
        return run_fn(args)

    return _handler


def _load_skill_modules() -> Dict[str, Handler]:
    registry: Dict[str, Handler] = {}
    if not _SKILLS_DIR.is_dir():
        return registry
    for path in sorted(_SKILLS_DIR.glob("*.py")):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        spec = importlib.util.spec_from_file_location(f"broker_skill_{path.stem}", path)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tool_name = getattr(mod, "TOOL_NAME", None)
        run_fn = getattr(mod, "run", None)
        if not tool_name or not callable(run_fn):
            continue
        registry[str(tool_name)] = _wrap_skill_run(run_fn)
    return registry


_BUILTIN: Dict[str, Handler] = {
    "mvn": _run_mvn,
    "curl": _run_curl,
}

_REGISTRY: Optional[Dict[str, Handler]] = None


def registry() -> Dict[str, Handler]:
    global _REGISTRY
    if _REGISTRY is None:
        merged = dict(_BUILTIN)
        merged.update(_load_skill_modules())
        _REGISTRY = merged
    return _REGISTRY


def list_tools() -> List[str]:
    return sorted(registry().keys())


def dispatch(
    tool: str,
    args: List[str],
    workdir: Path,
    prod_api_key: Optional[str],
) -> Tuple[int, str, str, List[str]]:
    handler = registry().get(tool)
    if handler is None:
        raise ValueError(f"unsupported tool: {tool}")
    return handler(args, workdir, prod_api_key)


def dispatch_scrubbed(
    tool: str,
    args: List[str],
    workdir: Path,
    prod_api_key: Optional[str],
) -> Tuple[int, str, str, bool]:
    code, stdout, stderr, secrets = dispatch(tool, args, workdir, prod_api_key)
    return (
        code,
        scrub_secrets(stdout, secrets),
        scrub_secrets(stderr, secrets),
        code == 0,
    )
