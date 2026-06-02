"""Workdir policy and output scrubbing."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List


def read_allowed_roots() -> List[Path]:
    roots_raw = os.environ.get("BROKER_ALLOWED_ROOTS", "").strip()
    roots: List[Path] = []
    if roots_raw:
        for part in roots_raw.split(","):
            p = part.strip()
            if p:
                roots.append(Path(p).expanduser())
    else:
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
            f"workdir not permitted: {resolved} "
            f"(allowed roots: {', '.join(str(r) for r in self.allowed_roots)})"
        )


def scrub_secrets(text: str, secrets: List[str]) -> str:
    out = text
    for s in secrets:
        if s:
            out = out.replace(s, "[REDACTED]")
    return out
