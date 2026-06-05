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

# Git describe for setup --check and upgrade visibility.
subro_version() {
  local root="${1:-}"
  if [[ -n "$root" ]] && git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$root" describe --tags --always --dirty 2>/dev/null \
      || git -C "$root" rev-parse --short HEAD 2>/dev/null \
      || echo "unknown"
    return 0
  fi
  echo "unknown"
}

# Start broker if needed (same on-demand behavior as ./bin/agent).
subro_ensure_broker() {
  local root="${1:?}"
  if "$root/bin/broker-daemon" status >/dev/null 2>&1; then
    return 0
  fi
  "$root/bin/broker-daemon" start >/dev/null 2>&1 || true
}

# Fingerprint skills/ for skip-if-unchanged sync in ./bin/agent.
subro_skills_fingerprint() {
  local root="$1"
  python3 - "${root}/skills" <<'PY'
import hashlib, os, sys

root = sys.argv[1]
if not os.path.isdir(root):
    print("none")
    raise SystemExit
h = hashlib.sha256()
for dirpath, _, files in os.walk(root):
    for name in sorted(files):
        if name == "SKILL.md":
            path = os.path.join(dirpath, name)
            st = os.stat(path)
            h.update(f"{path}:{st.st_mtime_ns}\n".encode())
print(h.hexdigest()[:16])
PY
}

# Run skills-sync only when skills/ changed (override: SUBRO_FORCE_SKILLS_SYNC=1).
subro_maybe_skills_sync() {
  local root="${1:?}"
  local stamp_file="${root}/.broker/.skills-sync-stamp"
  local fp

  if [[ "${SUBRO_FORCE_SKILLS_SYNC:-}" == "1" ]]; then
    "$root/bin/skills-sync" >/dev/null 2>&1 || true
    fp="$(subro_skills_fingerprint "$root")"
    mkdir -p "${root}/.broker"
    printf '%s' "$fp" >"$stamp_file"
    return 0
  fi

  fp="$(subro_skills_fingerprint "$root")"
  if [[ -f "$stamp_file" && "$(cat "$stamp_file")" == "$fp" ]]; then
    return 0
  fi
  "$root/bin/skills-sync" >/dev/null 2>&1 || true
  mkdir -p "${root}/.broker"
  printf '%s' "$fp" >"$stamp_file"
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
# Symlink broker interceptors into .agent-bin/ (first on PATH).
subro_prepare_interceptor_shims() {
  local workdir="${1:?}" root="${2:?}"
  local agent_bin="${workdir}/.agent-bin"
  local interceptors="${root}/interceptors"
  mkdir -p "$agent_bin"
  for shim in "$interceptors"/*; do
    [[ -f "$shim" && -x "$shim" ]] || continue
    local base
    base="$(basename "$shim")"
    [[ "$base" == "_broker_call.py" ]] && continue
    ln -sf "$shim" "${agent_bin}/${base}"
  done
}

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

# Pi bootstraps a loopback control plane (e.g. pi-cursor-provider). Pi mode only.
subro_append_seatbelt_pi_loopback() {
  local profile_file="${1:?}"
  cat >>"$profile_file" <<'EOF'
(allow network-bind (local ip "localhost:*"))
(allow network-inbound (local ip "localhost:*"))
(allow network-outbound (remote ip "localhost:*"))
EOF
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

# Sandbox backend: Ceiku/cplt (default) or native (Seatbelt/Landlock).
# Set SUBRO_SANDBOX in ~/.config/agent-broker/env. Default: cplt.
subro_sandbox_backend() {
  local b="${SUBRO_SANDBOX:-cplt}"
  case "$b" in
    native | cplt) printf '%s' "$b" ;;
    *)
      echo "subro: unknown SUBRO_SANDBOX=${b}; using cplt" >&2
      printf 'cplt'
      ;;
  esac
}

# Resolve cplt before any sandbox PATH mutation (host PATH may omit ~/.local/bin in agent-run).
subro_cplt_bin() {
  if [[ -n "${SUBRO_CPLT_BIN:-}" && -x "${SUBRO_CPLT_BIN}" ]]; then
    printf '%s' "${SUBRO_CPLT_BIN}"
    return 0
  fi
  command -v cplt 2>/dev/null || true
}

subro_cplt_available() {
  [[ -n "$(subro_cplt_bin)" ]]
}

# Map subro harness argv to cplt --agent mode. cplt --agent shell cannot exec bare
# command names (e.g. "pi", "bash"); use pi/opencode agents or shell -c instead.
# Sets: cplt_agent (string), cplt_cmd (array, may be empty for interactive shell).
subro_cplt_map_harness() {
  local harness="${1:?}"
  shift

  CPLT_AGENT=""
  CPLT_CMD=()

  case "$harness" in
    pi)
      CPLT_AGENT=pi
      CPLT_CMD=("$@")
      ;;
    opencode)
      CPLT_AGENT=opencode
      CPLT_CMD=("$@")
      ;;
    bash)
      CPLT_AGENT=shell
      if [[ "${1:-}" == "-lc" || "${1:-}" == "-c" ]]; then
        shift
        [[ $# -ge 1 ]] || return 2
        # Propagate inner exit code when cplt forwards shell status.
        CPLT_CMD=(-c "$1; __subro_rc=\$?; exit \$__subro_rc")
      elif [[ $# -gt 0 ]]; then
        CPLT_CMD=("$@")
      fi
      ;;
    *)
      CPLT_AGENT=shell
      CPLT_CMD=("$harness" "$@")
      ;;
  esac
}

# Run the agent command under Ceiku/cplt (external binary). Caller exports harness
# env vars before invoking. Does not nest with native Seatbelt/Landlock.
# cplt_bin must be an absolute or host-PATH-resolved path — not looked up after PATH is scrubbed.
subro_run_cplt_sandbox() {
  local sandbox_path="$1"
  local sock="$2"
  local root="$3"
  local cplt_bin="$4"
  shift 4

  if ! subro_cplt_map_harness "$@"; then
    echo "subro: invalid cplt harness invocation" >&2
    return 2
  fi

  # Broker UDS: connect-only via --allow-unix-socket (Ceiku/cplt; --allow-write no longer grants connect).
  local -a cplt_args=(--agent "$CPLT_AGENT" -y)
  if [[ -n "$sock" ]]; then
    cplt_args+=(--allow-unix-socket "$sock")
  fi

  # pi / opencode need loopback (TUI, harness IPC). Disable with SUBRO_CPLT_NO_LOCALHOST=1.
  if [[ "$CPLT_AGENT" == "pi" || "$CPLT_AGENT" == "opencode" ]]; then
    if [[ "${SUBRO_CPLT_NO_LOCALHOST:-}" != "1" ]]; then
      cplt_args+=(--allow-localhost-any)
    fi
  fi

  # Env for the sandboxed child (--pass-env). Do not use this PATH to find cplt.
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

  if [[ ${#CPLT_CMD[@]} -eq 0 ]]; then
    "$cplt_bin" "${cplt_args[@]}"
  else
    "$cplt_bin" "${cplt_args[@]}" -- "${CPLT_CMD[@]}"
  fi
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
