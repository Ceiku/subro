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

# Real pi harness dir (must be writable through kernel sandbox).
subro_export_pi_harness_env() {
  local real_home="${1:-$HOME}"
  export PI_CODING_AGENT_DIR="${PI_CODING_AGENT_DIR:-${real_home}/.pi/agent}"
}

# Host paths harness CLIs must write to (locks, sessions, auth). One per line.
subro_harness_write_paths() {
  local harness="${1:-}"
  case "$harness" in
    pi)
      [[ -n "${PI_CODING_AGENT_DIR:-}" ]] && printf '%s\n' "$PI_CODING_AGENT_DIR"
      ;;
    opencode)
      [[ -n "${OPENCODE_CONFIG_DIR:-}" ]] && printf '%s\n' "$OPENCODE_CONFIG_DIR"
      [[ -n "${OPENCODE_DATA_DIR:-}" ]] && printf '%s\n' "$OPENCODE_DATA_DIR"
      [[ -n "${OPENCODE_CACHE_DIR:-}" ]] && printf '%s\n' "$OPENCODE_CACHE_DIR"
      [[ -n "${OPENCODE_STATE_DIR:-}" ]] && printf '%s\n' "$OPENCODE_STATE_DIR"
      ;;
  esac
}

# Append Seatbelt write rules for harness host dirs to a profile file.
subro_append_seatbelt_harness_writes() {
  local harness="${1:-}"
  local profile_file="${2:?}"
  local wp
  while IFS= read -r wp; do
    [[ -n "$wp" ]] || continue
    printf '(allow file-write* (subpath "%s"))\n' "$wp" >>"$profile_file"
  done < <(subro_harness_write_paths "$harness")
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

# Resolve landlock-restrict binary (Linux sandbox helper).
# Optional arg: repo root (defaults to SUBRO_ROOT).
subro_landlock_restrict_bin() {
  local root="${1:-${SUBRO_ROOT:-}}"
  if [[ -n "${SUBRO_LANDLOCK_RESTRICT:-}" && -x "${SUBRO_LANDLOCK_RESTRICT}" ]]; then
    echo "${SUBRO_LANDLOCK_RESTRICT}"
    return 0
  fi
  if [[ -n "$root" && -x "${root}/tools/landlock-restrict/landlock-restrict" ]]; then
    echo "${root}/tools/landlock-restrict/landlock-restrict"
    return 0
  fi
  command -v landlock-restrict 2>/dev/null || true
}

# Sandbox backend: native (Seatbelt/Landlock) or optional external cplt (MIT).
# Set SUBRO_SANDBOX in ~/.config/agent-broker/env. Default: native.
subro_sandbox_backend() {
  local b="${SUBRO_SANDBOX:-native}"
  case "$b" in
    native | cplt) printf '%s' "$b" ;;
    *)
      echo "subro: unknown SUBRO_SANDBOX=${b}; using native" >&2
      printf 'native'
      ;;
  esac
}

subro_cplt_available() {
  command -v cplt >/dev/null 2>&1
}

# Run the agent command under navikt/cplt (external binary). Caller exports harness
# env vars before invoking. Does not nest with native Seatbelt/Landlock.
subro_run_cplt_sandbox() {
  local sandbox_path="$1"
  local sock="$2"
  local root="$3"
  shift 3

  local sock_dir
  sock_dir="$(dirname "$sock")"
  local -a cplt_args=(--agent shell -y --allow-write "$sock_dir")

  export PATH="$sandbox_path"
  export BROKER_SOCK="$sock"
  export SUBRO_ROOT="$root"

  cplt_args+=(--pass-env PATH --pass-env BROKER_SOCK --pass-env SUBRO_ROOT)
  [[ -n "${BROKER_SOCKET_TOKEN:-}" ]] && cplt_args+=(--pass-env BROKER_SOCKET_TOKEN)
  [[ -n "${PI_CODING_AGENT_DIR:-}" ]] && cplt_args+=(--pass-env PI_CODING_AGENT_DIR)
  [[ -n "${PI_CODING_AGENT_SESSION_DIR:-}" ]] && cplt_args+=(--pass-env PI_CODING_AGENT_SESSION_DIR)
  [[ -n "${OPENCODE_CONFIG_DIR:-}" ]] && cplt_args+=(--pass-env OPENCODE_CONFIG_DIR)
  [[ -n "${OPENCODE_DATA_DIR:-}" ]] && cplt_args+=(--pass-env OPENCODE_DATA_DIR)
  [[ -n "${OPENCODE_CACHE_DIR:-}" ]] && cplt_args+=(--pass-env OPENCODE_CACHE_DIR)
  [[ -n "${OPENCODE_STATE_DIR:-}" ]] && cplt_args+=(--pass-env OPENCODE_STATE_DIR)
  [[ -n "${OPENCODE_CONFIG:-}" ]] && cplt_args+=(--pass-env OPENCODE_CONFIG)

  cplt "${cplt_args[@]}" -- "$@"
}

# Print one-line Landlock status for doctor/setup. Returns 0 when usable.
subro_landlock_status() {
  local root="${1:-}"
  local bin

  if [[ "$(uname -s)" != "Linux" ]]; then
    echo "n/a (not Linux)"
    return 0
  fi

  bin="$(subro_landlock_restrict_bin "$root")"
  if [[ -z "$bin" ]]; then
    echo "missing (run ./bin/build-landlock-restrict or install landlock-restrict on PATH)"
    return 1
  fi

  if "$bin" --help >/dev/null 2>&1; then
    echo "available: $bin"
    return 0
  fi

  echo "broken: $bin (--help failed)"
  return 1
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
