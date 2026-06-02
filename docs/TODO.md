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
| P3.3 | Linux Landlock CI / real binary | todo | |
| P3.4 | Integration test script | todo | |

## P4 — Future (from planning doc)

| ID | Item | Status |
|----|------|--------|
| P4.1 | Runtime `register-skill` over UDS | done | `register-skill` CLI + `.agent-bin/` shims |
| P4.2 | Agent package manager / lockfile | done | `bin/apm`, `subro.lock.json`, `packages/*/apm.yml` |
| P4.3 | PII scrubber (Presidio / regex pack) | done | `broker/scrub.py` regex pack (default on) |
| P4.4 | MCP or STDIO broker transport | done | `bin/broker-stdio` + `broker/stdio_main.py` |
