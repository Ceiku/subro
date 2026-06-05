# Kernel-sandboxed agent + privileged broker (UDS)

> **Work in progress — proof of concept.** This project is experimental and not production-ready. APIs, sandbox policies, and broker behavior may change without notice. Use it to explore the architecture and provide feedback; do not rely on it for security-critical workloads yet.

This repo provides a **local, high-performance tool-execution split**:

- A **sandboxed agent process** runs with a scrubbed environment and kernel-level filesystem restrictions.
- For sensitive tools (`mvn`, `curl` when it contains a placeholder key), lightweight **interceptors** forward the request to a **privileged broker** over a **Unix Domain Socket**.
- The broker executes the real tool with host privileges, injects secrets, **scrubs sensitive strings** from outputs, and returns safe results.

## What this solves (security)

This is designed for running CLI-based coding agents safely in hostile conditions (prompt injection, malicious repos, untrusted build output).

- **Secret isolation**
  - The agent process starts under `env -i` (no inherited env vars) and runs with a **fake `HOME`** in the working directory.
  - High-privilege secrets live **only** in the broker’s environment (loaded from `~/.config/agent-broker/env` by default), not in the agent.

- **Kernel-enforced filesystem boundaries**
  - The agent is allowed to read/write the current working directory (your repo) and the broker socket.
  - The agent is explicitly denied access to common sensitive locations like `~/.ssh`, `~/.m2`, and shell startup files.
  - By default it also denies common ecosystem secret/config files used for dependency fetching and publishing (npm/pnpm/pip), such as `~/.npmrc`, `~/.config/pnpm`, `~/.config/pip`, `.netrc`, and repo-level `.npmrc`.

- **Transparent, enforced tool mediation**
  - Even if an agent “forgets” instructions, `PATH` is arranged so `mvn` and `curl` resolve to **wrappers** first.
  - Those wrappers forward structured requests to the broker, so privileged actions happen in a single choke point you control.

- **Output scrubbing before the LLM sees it**
  - For `curl`, the broker replaces `X-PROD-KEY` with the real `PROD_API_KEY`, then scrubs that key from stdout/stderr before returning output.
  - (Extendable to broader PII/credential scrubbing as you add more tools.)

### Threat model notes / non-goals

- **This does not make untrusted code “safe to execute.”** If your build/test process runs arbitrary code, it can still do damage inside the allowed workspace or via allowed network.
- **Broker is the trust boundary.** Keep the broker allowlist small and inputs strictly validated; do not add “run arbitrary command” functionality.
- **Repo `.env` files are treated as sensitive by default** for the agent (Pattern A below).

## File layout

```text
.
├── README.md
├── bin/
│   ├── agent              # start broker + sandboxed CLI
│   ├── agent-run
│   ├── broker-daemon
│   ├── doctor             # verify install
│   ├── skill-init         # scaffold a new skill
│   └── setup
├── broker/
│   ├── main.py
│   ├── handlers.py        # tool registry
│   └── skills/            # drop-in skill modules
├── interceptors/
│   ├── _broker_call.py    # shared UDS client
│   ├── mvn
│   ├── curl
│   └── entur-departures
├── skills/                # SKILL.md for agents
└── docs/TODO.md           # prioritized roadmap
```

## Adding a new skill

```bash
./bin/skill-init my-api-skill
# edit broker/skills/my_api_skill.py (TOOL_NAME + run())
./bin/broker-daemon stop && ./bin/broker-daemon start
./bin/doctor
```

Skills in `broker/skills/*.py` are auto-registered if they export `TOOL_NAME` and `run(args)`.
Add a thin `interceptors/<name>` (created by `skill-init`) and `skills/<name>/SKILL.md` for the LLM.

## Showcase skill: Entur departures (read-only API)

Demonstrates a **broker-guarded API skill**: the agent calls a normal CLI, but the broker enforces an allowlist and fixed query shape (no arbitrary HTTP/GraphQL from the sandbox).

```bash
./bin/agent-run bash -lc 'entur-departures jernbanetorget'
./bin/agent-run bash -lc 'entur-departures nationaltheatret 8'
./bin/agent-run bash -lc 'entur-departures oslo-s'
```

**Allowed stops only:** `jernbanetorget`, `nationaltheatret`, `oslo-s` (lookup/read-only; broker uses Entur’s public Journey Planner API with a fixed departure query).

Optional broker env: `ENTUR_CLIENT_NAME=subro-yourname` (defaults to `subro-agent-broker`).

Agent instructions: `skills/entur-departures/SKILL.md`.

## Harness integration (pi.dev / Cursor)

```bash
./bin/skills-sync   # links skills → .cursor/skills, .pi/skills; updates AGENTS.md
./bin/agent pi.dev  # auto-runs skills-sync + broker + sandbox
```

See [docs/P1-P4.md](docs/P1-P4.md) for `register-skill`, `apm`, PII scrubbing, and STDIO broker.

## Quick start

### 0) One-time setup

```bash
./bin/setup
# Edit ~/.config/agent-broker/env — set BROKER_ALLOWED_ROOTS to your project paths
./bin/doctor
```

### Run any CLI through the sandbox

```bash
./bin/agent bash          # sandboxed shell
./bin/agent pi.dev          # example harness
```

### 1) Start the broker (privileged host process)

The broker loads secrets from an **env file** (default: `~/.config/agent-broker/env`).

Seed the broker with:

- `PROD_API_KEY`: used to replace `X-PROD-KEY` in `curl` requests
- `BROKER_ALLOWED_ROOTS`: comma-separated list of directories the broker will accept as `workdir`
  - Recommended: set it to **this repo root** (and any other explicit workspaces you want)
- `BROKER_SOCK` (optional): override the default socket path (see below)
- `BROKER_SOCKET_TOKEN`: auto-generated by `setup`; required on broker requests when set
- `BROKER_AUDIT_LOG` (optional): JSONL audit trail (default `~/.config/agent-broker/audit.jsonl`)

From the repo root:

```bash
export BROKER_ENV_FILE="$HOME/.config/agent-broker/env"
./bin/broker-daemon start
./bin/broker-daemon status
```

Logs go to `./.broker/log.txt`.

To stop:

```bash
./bin/broker-daemon stop
```

### 2) Run a sandboxed agent command

The sandbox wrapper clears the environment (`env -i`), sets a minimal `PATH` that prefers `./interceptors`, and tries to enforce kernel sandboxing:

- macOS: `sandbox-exec` (Seatbelt)
- Linux: `landlock-restrict` (if installed)

Example (replace with your agent CLI):

```bash
./bin/agent-run bash -lc 'which mvn; mvn -v'
./bin/agent-run bash -lc 'curl -sS https://example.com | head -c 200; echo'
./bin/agent-run bash -lc 'curl -sS -H "Authorization: Bearer X-PROD-KEY" https://example.com | head -c 200; echo'
```

Behavior:

- `mvn` inside the sandbox is intercepted and executed by the broker using host `~/.m2/settings.xml`.
- `curl` is intercepted **only** if args contain `X-PROD-KEY`; otherwise it runs `/usr/bin/curl` inside the sandbox.

Pattern A note: many projects keep a repo `.env` for humans. This setup keeps that working for you, but the **sandboxed agent is explicitly denied** reading common `.env*` files in the current directory. This avoids the “agent can read repo secrets” trap while preserving normal local dev. Put high-privilege secrets in the broker env file instead.

## Socket path defaults

The broker socket path is chosen per OS (override with `BROKER_SOCK`):

- **macOS**: `~/Library/Application Support/agent-broker/agent-broker.sock`
- **Linux**: `$XDG_RUNTIME_DIR/agent-broker/agent-broker.sock` (fallback `/tmp/agent-broker/agent-broker.sock`)

### 3) (Optional) Install interceptors into a dedicated PATH dir

`agent-run` already prepends `./interceptors` to `PATH`, so this is optional. If you want a dedicated directory of symlinks:

```bash
./bin/install-interceptors
ls -la ./.agent-path
```

## Security notes / constraints

- The sandbox wrapper intentionally sets a **fake HOME** under the current directory (`./.agent-home`) to avoid reading host dotfiles.
- The broker **validates** `workdir` by resolving symlinks (`realpath`) and ensuring it is within `BROKER_ALLOWED_ROOTS`.
- The broker uses `subprocess.run([...], shell=False)` only, preventing shell-injection through args.
- The broker scrubs `PROD_API_KEY` from returned stdout/stderr.

## Permissions

Make scripts executable:

```bash
chmod +x bin/* interceptors/*
```

## License (Fair Source — FSL-1.1-ALv2)

SPDX: `FSL-1.1-ALv2`

Licensed under the [Functional Source License, Version 1.1, ALv2 Future
License](LICENSE). This is **fair source**: use and modify freely for permitted
purposes; **competing commercial use** is restricted until each version converts
to **Apache 2.0** two years after release (DOSP).

- Summary: [FAIR-SOURCE.md](FAIR-SOURCE.md)
- Trademarks: [TRADEMARK.md](TRADEMARK.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)

## Roadmap

See [docs/TODO.md](docs/TODO.md) for prioritized security and platform work.

