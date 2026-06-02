"""Runtime skill registration (project-local scripts under .agent-skills/)."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_SKILLS_SUBDIR = ".agent-skills"


class RegisterSkillSpec(BaseModel):
    name: str = Field(min_length=1)
    script_relpath: str = Field(min_length=1)
    required_secrets: List[str] = Field(default_factory=list)


def _registry_path() -> Path:
    raw = os.environ.get("BROKER_REGISTERED_SKILLS", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".config" / "agent-broker" / "registered-skills.json"


def load_registered() -> Dict[str, Any]:
    path = _registry_path()
    if not path.is_file():
        return {"skills": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"skills": []}
    if not isinstance(data, dict) or "skills" not in data:
        return {"skills": []}
    return data


def save_registered(data: Dict[str, Any]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _validate_script(workdir: Path, script_relpath: str) -> Path:
    rel = Path(script_relpath)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("script_relpath must be relative without ..")
    if rel.parts[0] != _SKILLS_SUBDIR:
        raise ValueError(f"script must live under {_SKILLS_SUBDIR}/")
    script = (workdir / rel).resolve()
    skills_root = (workdir / _SKILLS_SUBDIR).resolve()
    try:
        script.relative_to(skills_root)
    except ValueError as e:
        raise ValueError("script path escapes .agent-skills") from e
    if not script.is_file():
        raise ValueError(f"script not found: {script_relpath}")
    return script


def register_skill(spec: RegisterSkillSpec, workdir: Path) -> Tuple[int, str, str]:
    if not _NAME_RE.match(spec.name):
        return 2, "", f"invalid skill name: {spec.name!r}\n"

    try:
        script = _validate_script(workdir, spec.script_relpath)
    except ValueError as e:
        return 2, "", f"{e}\n"

    missing = [s for s in spec.required_secrets if not os.environ.get(s)]
    if missing:
        return 2, "", f"missing broker env secrets: {', '.join(missing)}\n"

    data = load_registered()
    skills: List[Dict[str, Any]] = list(data.get("skills") or [])
    entry = {
        "name": spec.name,
        "script": str(script),
        "workdir_root": str(workdir),
        "required_secrets": spec.required_secrets,
    }
    skills = [s for s in skills if s.get("name") != spec.name]
    skills.append(entry)
    data["skills"] = skills
    save_registered(data)

    _write_agent_bin_wrapper(workdir, spec.name)

    out = json.dumps({"ok": True, "registered": spec.name, "script": spec.script_relpath}, indent=2)
    return 0, out + "\n", ""


def _write_agent_bin_wrapper(workdir: Path, skill_name: str) -> None:
    """Create project-local CLI shim (.agent-bin/<skill>) for sandbox PATH."""
    agent_bin = workdir / ".agent-bin"
    agent_bin.mkdir(parents=True, exist_ok=True)
    wrapper = agent_bin / skill_name
    wrapper.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
SUBRO_ROOT="${{SUBRO_ROOT:-}}"
if [[ -z "$SUBRO_ROOT" || ! -x "$SUBRO_ROOT/interceptors/_broker_call.py" ]]; then
  echo "SUBRO_ROOT not set or subro interceptors missing" >&2
  exit 1
fi
exec env TMPDIR="${{TMPDIR:-/tmp}}" PYTHONDONTWRITEBYTECODE=1 \\
  python3 "$SUBRO_ROOT/interceptors/_broker_call.py" {skill_name} "$@"
""",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)


def run_registered_skill(
    name: str,
    args: List[str],
    workdir: Path,
) -> Tuple[int, str, str, List[str]]:
    data = load_registered()
    secrets_to_scrub: List[str] = []
    for entry in data.get("skills") or []:
        if entry.get("name") != name:
            continue
        script = Path(entry["script"])
        root = Path(entry.get("workdir_root", workdir))
        try:
            workdir.resolve().relative_to(root.resolve())
        except ValueError as e:
            raise ValueError(f"workdir not under registered skill root for {name}") from e
        if not script.is_file():
            raise ValueError(f"registered script missing: {script}")

        env = os.environ.copy()
        for key in entry.get("required_secrets") or []:
            val = os.environ.get(key, "")
            if val:
                env[key] = val
                secrets_to_scrub.append(val)
        proc = subprocess.run(
            [os.environ.get("PYTHON", "python3"), str(script), *args],
            cwd=str(workdir),
            env=env,
            shell=False,
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or "", secrets_to_scrub

    raise ValueError(f"unsupported tool: {name}")
