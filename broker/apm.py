#!/usr/bin/env python3
"""Agent package manager: install skill packages into subro layout."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def _load_yaml(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    # Minimal fallback without PyYAML
    out: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_lock(lock_path: Path) -> Dict[str, Any]:
    if not lock_path.is_file():
        return {"version": 1, "packages": []}
    return json.loads(lock_path.read_text(encoding="utf-8"))


def save_lock(lock_path: Path, data: Dict[str, Any]) -> None:
    lock_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def install_package(pkg_dir: Path, repo_root: Path) -> Dict[str, Any]:
    manifest = pkg_dir / "apm.yml"
    if not manifest.is_file():
        raise ValueError(f"apm.yml not found in {pkg_dir}")

    meta = _load_yaml(manifest)
    name = str(meta.get("name", pkg_dir.name))
    version = str(meta.get("version", "0.0.0"))
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid package name: {name}")

    def resolve(rel: str) -> Path:
        p = (pkg_dir / rel).resolve()
        if not p.is_file() and not p.is_dir():
            raise ValueError(f"missing package file: {rel}")
        return p

    skill_md_src = resolve(str(meta.get("skill_md", f"skills/{name}/SKILL.md")))
    broker_skill_src = resolve(str(meta.get("broker_skill", f"broker/skills/{name.replace('-', '_')}.py")))
    interceptor_src = resolve(str(meta.get("interceptor", f"interceptors/{name}")))

    def _copy_if_different(src: Path, dest: Path) -> None:
        src_r = src.resolve()
        dest_r = dest.resolve()
        if src_r == dest_r:
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    skill_dest = repo_root / "skills" / name
    skill_dest.mkdir(parents=True, exist_ok=True)
    _copy_if_different(skill_md_src, skill_dest / "SKILL.md")

    broker_dest = repo_root / "broker" / "skills" / broker_skill_src.name
    _copy_if_different(broker_skill_src, broker_dest)

    interceptor_dest = repo_root / "interceptors" / name
    _copy_if_different(interceptor_src, interceptor_dest)
    interceptor_dest.chmod(0o755)

    entry = {
        "name": name,
        "version": version,
        "source": str(pkg_dir.resolve()),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            "skill_md": _sha256_file(skill_dest / "SKILL.md"),
            "broker_skill": _sha256_file(broker_dest),
            "interceptor": _sha256_file(interceptor_dest),
        },
        "requires_env": meta.get("requires_env") or [],
    }
    return entry


def install(packages: List[Path], repo_root: Path, lock_path: Path) -> List[str]:
    lock = load_lock(lock_path)
    installed_names = {p["name"]: i for i, p in enumerate(lock.get("packages") or [])}
    messages: List[str] = []

    for pkg_dir in packages:
        entry = install_package(pkg_dir, repo_root)
        name = entry["name"]
        if name in installed_names:
            lock["packages"][installed_names[name]] = entry
            messages.append(f"updated {name}@{entry['version']}")
        else:
            lock.setdefault("packages", []).append(entry)
            messages.append(f"installed {name}@{entry['version']}")

    save_lock(lock_path, lock)
    return messages
