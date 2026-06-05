# Prioritized roadmap

Status legend: `done` | `partial` | `todo`

## P0 — Platform foundation (shipability)

| ID | Item | Status | Notes |
|----|------|--------|-------|
| P0.1 | Shared UDS client (`interceptors/_broker_call.py`) | done | DRY all interceptors |
| P0.2 | Broker tool registry (`broker/handlers.py`) | done | No `main.py` edit per skill |
| P0.3 | Skill discovery (`broker/skills/*.py`) | done | `TOOL_NAME` + `run()` |
| P0.4 | `bin/doctor` verify command | done | broker, socket, tools, sandbox smoke |
| P0.5 | `bin/agent` launcher (broker + sandbox) | done | Single entry for pi.dev / CLIs |

## P1 — Skill authoring UX

| ID | Item | Status | Notes |
|----|------|--------|-------|
| P1.1 | `bin/skill-init <name>` scaffold | done | skill module + interceptor + SKILL.md |
| P1.2 | Document skill contract in README | done | TOOL_NAME, run(), restart broker |
| P1.3 | Harness skill loading (pi.dev / Cursor) | done | `bin/skills-sync`, `.cursor/`, `.pi/`, `AGENTS.md` |

## P2 — Security hardening

| ID | Item | Status | Notes |
|----|------|--------|-------|
| P2.1 | UDS token auth (`BROKER_SOCKET_TOKEN`) | done | optional; enforced if set |
| P2.2 | Audit log (JSONL) | done | `BROKER_AUDIT_LOG` |
| P2.3 | macOS Seatbelt read allowlist | partial | subpath-only reads abort bash; kept denylist model for now |
| P2.4 | Broker curl host allowlist | todo | |
| P2.5 | Maven invocation allowlist | todo | e.g. only `test`, `compile` |
| P2.6 | Block `/usr/bin/curl` bypass for broker-only APIs | todo | wrapper or deny |

## P3 — Operations & docs

| ID | Item | Status | Notes |
|----|------|--------|-------|
| P3.1 | README overhaul (remove repo-create boilerplate) | done | |
| P3.2 | `setup` generates socket token | done | |
| P3.3 | Linux Landlock CI / real binary | done | vendored `tools/landlock-restrict`, `bin/build-landlock-restrict`, doctor/setup detection, `.github/workflows/linux-landlock.yml` |
| P3.4 | Integration test script | todo | |
| P3.5 | Fair Source license (FSL-1.1-ALv2) | done | `LICENSE`, `FAIR-SOURCE.md`, `CONTRIBUTING.md`, `TRADEMARK.md` |
| P3.6 | First-class `./bin/agent pi` integration | done | shims, `PI_CODING_AGENT_DIR`, `--global-pi` |
| P3.7 | Harness env var docs | done | README table + global pi settings |
| P3.8 | Doctor in-sandbox broker tests | done | UDS + entur smoke inside sandbox |
| P3.9 | `BROKER_ALLOWED_ROOTS` validation | done | `setup` + `doctor` via `bin/_lib.sh` |
| P3.10 | Fix `SUBRO_NO_SANDBOX=1` | done | `sandbox_env` function no longer exec'd |
| P3.11 | Broker lifecycle docs + stale socket/pid | done | `broker-daemon status`, README |
| P3.12 | First-class `./bin/agent opencode` integration | done | shims, `OPENCODE_*_DIR`, `--global-opencode` |
| P3.13 | Harness sandbox write allowlist (pi/opencode host dirs) | done | `~/.pi/agent`, `OPENCODE_*` dirs writable in harness modes |
| P3.14 | Pi loopback bind in Seatbelt (TUI / print mode) | done | `network-bind` + inbound on `localhost:*`, pi mode only |

## P4 — Future (from planning doc)

| ID | Item | Status |
|----|------|--------|
| P4.1 | Runtime `register-skill` over UDS | done | `register-skill` CLI + `.agent-bin/` shims |
| P4.2 | Agent package manager / lockfile | done | `bin/apm`, `subro.lock.json`, `packages/*/apm.yml` |
| P4.3 | PII scrubber (Presidio / regex pack) | done | `broker/scrub.py` regex pack (default on) |
| P4.4 | MCP or STDIO broker transport | done | `bin/broker-stdio` + `broker/stdio_main.py` |
