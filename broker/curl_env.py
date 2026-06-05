"""Substitute $VAR / ${VAR} in curl args from broker host environment."""
from __future__ import annotations

import os
import re
from typing import Dict, List, Sequence, Tuple

_ENV_REF_BRACE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_ENV_REF = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

# Never inject broker/runtime vars into outbound curl (agent-controlled args).
_DENY_EXACT = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "PWD",
        "OLDPWD",
        "SHLVL",
        "LANG",
        "LC_ALL",
        "TERM",
        "TMPDIR",
        "HOSTNAME",
        "XDG_RUNTIME_DIR",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "PYTHONDONTWRITEBYTECODE",
    }
)
_DENY_PREFIXES = ("BROKER_", "SUBRO_")


def _substitution_allowed(name: str) -> bool:
    if name in _DENY_EXACT:
        return False
    return not any(name.startswith(p) for p in _DENY_PREFIXES)


def env_refs_in_text(text: str) -> List[str]:
    """Unique env var names referenced as $VAR or ${VAR} in text."""
    seen: set[str] = set()
    names: List[str] = []
    for pattern in (_ENV_REF_BRACE, _ENV_REF):
        for match in pattern.finditer(text):
            name = match.group(1)
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def args_refer_env_vars(args: Sequence[str]) -> bool:
    return any(env_refs_in_text(a) for a in args)


def substitute_curl_args(
    args: Sequence[str],
    env: Dict[str, str] | None = None,
) -> Tuple[List[str], List[str], List[str]]:
    """
    Replace $VAR / ${VAR} in each arg when VAR is set in env and allowed.
    Returns (new_args, secrets_for_scrubbing, substituted_var_names).
    """
    source = env if env is not None else os.environ
    secrets: List[str] = []
    substituted_vars: List[str] = []
    out: List[str] = []

    for arg in args:
        new_arg = arg
        for name in env_refs_in_text(arg):
            if not _substitution_allowed(name):
                continue
            value = source.get(name)
            if not value:
                continue
            new_arg = new_arg.replace(f"${{{name}}}", value)
            new_arg = new_arg.replace(f"${name}", value)
            secrets.append(value)
            substituted_vars.append(name)
        out.append(new_arg)

    return out, secrets, substituted_vars
