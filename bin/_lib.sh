# Shared helpers for subro bin scripts. Source, do not execute.
# shellcheck shell=bash

subro_default_sock() {
  case "$(uname -s)" in
    Darwin) echo "${HOME}/Library/Application Support/agent-broker/agent-broker.sock" ;;
    Linux) echo "${XDG_RUNTIME_DIR:-/tmp}/agent-broker/agent-broker.sock" ;;
    *) echo "/tmp/agent-broker/agent-broker.sock" ;;
  esac
}

subro_load_broker_env() {
  local env_file="${BROKER_ENV_FILE:-${HOME}/.config/agent-broker/env}"
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
}

subro_trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  s="${s%\"}"
  s="${s#\"}"
  printf '%s' "$s"
}

# Warn if BROKER_ALLOWED_ROOTS paths are missing or omit cwd.
# Usage: subro_validate_broker_roots warn|fail [cwd]
subro_validate_broker_roots() {
  local mode="${1:-warn}"
  local cwd="${2:-$(pwd)}"
  local roots="${BROKER_ALLOWED_ROOTS:-}"
  local r covered=0 missing=0

  if [[ -z "$roots" ]]; then
    if [[ "$mode" == "fail" ]]; then
      echo "  FAIL: BROKER_ALLOWED_ROOTS unset" >&2
      return 1
    fi
    echo "  WARN: BROKER_ALLOWED_ROOTS unset (broker defaults to its cwd)" >&2
    return 0
  fi

  local IFS=,
  for r in $roots; do
    r="$(subro_trim "$r")"
    [[ -n "$r" ]] || continue
    if [[ ! -d "$r" ]]; then
      echo "  WARN: BROKER_ALLOWED_ROOTS path does not exist: $r" >&2
      missing=1
    fi
    case "$cwd" in
      "$r" | "$r"/*) covered=1 ;;
    esac
  done

  if [[ "$covered" -eq 0 ]]; then
    echo "  WARN: BROKER_ALLOWED_ROOTS does not include current directory: $cwd" >&2
    echo "        Add it to ~/.config/agent-broker/env (comma-separated list)." >&2
    missing=1
  fi

  if [[ "$missing" -eq 1 && "$mode" == "fail" ]]; then
    return 1
  fi
  return 0
}

# Symlink pi + node into workdir/.agent-bin for sandboxed PATH.
subro_prepare_pi_shims() {
  local workdir="${1:-$(pwd)}"
  local agent_bin="${workdir}/.agent-bin"
  local pi_bin node_bin

  pi_bin="$(command -v pi 2>/dev/null || true)"
  node_bin="$(command -v node 2>/dev/null || true)"

  if [[ -z "$pi_bin" ]]; then
    echo "pi not found on PATH (install: npm i -g @earendil-works/pi-coding-agent)" >&2
    return 1
  fi
  if [[ -z "$node_bin" ]]; then
    echo "node not found on PATH (required by pi)" >&2
    return 1
  fi

  mkdir -p "$agent_bin"
  ln -sfn "$pi_bin" "${agent_bin}/pi"
  ln -sfn "$node_bin" "${agent_bin}/node"
}

# Merge repo skills/ into ~/.pi/agent/settings.json (absolute path).
subro_sync_pi_global_skills() {
  local root="$1"
  local skills_dir="${root}/skills"
  local settings="${HOME}/.pi/agent/settings.json"

  [[ -d "$skills_dir" ]] || return 0

  python3 - "$skills_dir" "$settings" <<'PY'
import json, os, sys
skills_dir = os.path.abspath(sys.argv[1])
settings_path = os.path.expanduser(sys.argv[2])
os.makedirs(os.path.dirname(settings_path), exist_ok=True)
data = {}
if os.path.isfile(settings_path):
    with open(settings_path) as f:
        data = json.load(f)
skills = data.get("skills") or []
if not isinstance(skills, list):
    skills = []
if skills_dir not in skills:
    skills.append(skills_dir)
    data["skills"] = skills
    with open(settings_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Added {skills_dir} to {settings_path}")
PY
}
