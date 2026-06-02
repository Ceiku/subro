#!/usr/bin/env python3
"""Template for new broker skills (see bin/skill-init)."""
from __future__ import annotations

from typing import List, Tuple

TOOL_NAME = "my-skill"


def run(args: List[str]) -> Tuple[int, str, str, List[str]]:
    if not args or args[0] in ("-h", "--help"):
        return 0, f"Usage: {TOOL_NAME} <args...>\n", "", []
    return 2, "", "not implemented\n", []
