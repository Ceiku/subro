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

# Symlink node + named CLIs into workdir/.agent-bin for sandbox PATH.
subro_prepare_node_cli_shims() {
  local workdir="$1"
  shift
  local agent_bin="${workdir}/.agent-bin"
  local node_bin cmd_bin cmd

  node_bin="$(command -v node 2>/dev/null || true)"
  if [[ -z "$node_bin" ]]; then
    echo "node not found on PATH (required for Node-based agent CLIs)" >&2
    return 1
  fi

  mkdir -p "$agent_bin"
  ln -sfn "$node_bin" "${agent_bin}/node"

  for cmd in "$@"; do
    cmd_bin="$(command -v "$cmd" 2>/dev/null || true)"
    if [[ -z "$cmd_bin" ]]; then
      echo "$cmd not found on PATH" >&2
      return 1
    fi
    ln -sfn "$cmd_bin" "${agent_bin}/${cmd}"
  done
}

# Symlink pi + node into workdir/.agent-bin for sandboxed PATH.
subro_prepare_pi_shims() {
  subro_prepare_node_cli_shims "${1:?}" pi
}

# Point OpenCode at the real harness dirs (sandbox uses a fake HOME).
subro_export_opencode_harness_env() {
  local real_home="${1:-$HOME}"
  export OPENCODE_CONFIG_DIR="${OPENCODE_CONFIG_DIR:-${real_home}/.config/opencode}"
  export OPENCODE_DATA_DIR="${OPENCODE_DATA_DIR:-${real_home}/.local/share/opencode}"
  export OPENCODE_CACHE_DIR="${OPENCODE_CACHE_DIR:-${real_home}/.cache/opencode}"
  export OPENCODE_STATE_DIR="${OPENCODE_STATE_DIR:-${real_home}/.local/state/opencode}"
}

# Symlink opencode (+ node, optional bun) into .agent-bin.
subro_prepare_opencode_shims() {
  local workdir="${1:?}"
  subro_prepare_node_cli_shims "$workdir" opencode || return 1
  local bun_bin
  bun_bin="$(command -v bun 2>/dev/null || true)"
  if [[ -n "$bun_bin" ]]; then
    ln -sfn "$bun_bin" "${workdir}/.agent-bin/bun"
  fi
}

# Symlink each skills/<name>/ into a harness skills directory.
subro_link_skills_tree() {
  local root="$1"
  local dest_root="$2"
  local skills_src="${root}/skills"
  local skill_dir name

  [[ -d "$skills_src" ]] || return 0
  mkdir -p "$dest_root"
  for skill_dir in "$skills_src"/*; do
    [[ -d "$skill_dir" ]] || continue
    [[ -f "$skill_dir/SKILL.md" ]] || continue
    name="$(basename "$skill_dir")"
    ln -sfn "$skill_dir" "${dest_root}/${name}"
  done
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

# Symlink skills into ~/.config/opencode/skills/ for global harness users.
subro_sync_opencode_global_skills() {
  local root="$1"
  local dest="${HOME}/.config/opencode/skills"
  subro_link_skills_tree "$root" "$dest"
}
