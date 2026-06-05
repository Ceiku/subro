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

## Harness integration (pi / OpenCode / Cursor)

Subro includes **first-class harness modes** for Node-based agent CLIs. Run from any project directory under `BROKER_ALLOWED_ROOTS` — not only inside this repo.

```bash
./bin/skills-sync                    # .cursor/, .pi/, .opencode/, .agents/ symlinks
./bin/skills-sync --global-pi        # merge skills/ → ~/.pi/agent/settings.json
./bin/skills-sync --global-opencode  # symlink skills/ → ~/.config/opencode/skills/
./bin/agent pi                       # pi coding agent
./bin/agent opencode                 # OpenCode agent
```

Each `./bin/agent <harness>` mode:

- starts the broker (on demand)
- symlinks the CLI (+ `node`) into `./.agent-bin/` (sandbox `PATH`)
- points harness config at your **real** `~` dirs (sandbox uses fake `HOME=./.agent-home`)
- syncs broker skills into global harness config when needed

See [docs/P1-P4.md](docs/P1-P4.md) for `register-skill`, `apm`, PII scrubbing, and STDIO broker.

### Running Node / Rust / Python agent CLIs

The sandbox sets `HOME` to `./.agent-home`, so harnesses that store config under `~` need an explicit override:

| Harness | Gotcha | Fix |
|---------|--------|-----|
| **pi** | fake `HOME` hides `~/.pi/agent` | `PI_CODING_AGENT_DIR` (automatic via `./bin/agent pi`) |
| **pi** | locks/sessions under `~/.pi/agent` | Seatbelt/Landlock write allowlist for that dir in pi mode |
| **pi** | `pi` / `node` not on sandbox `PATH` | shims in `./.agent-bin/` |
| **OpenCode** | fake `HOME` hides `~/.config/opencode` and `~/.local/share/opencode` | `OPENCODE_CONFIG_DIR`, `OPENCODE_DATA_DIR`, etc. (automatic via `./bin/agent opencode`) |
| **OpenCode** | global skills not in project `.opencode/` | `./bin/skills-sync --global-opencode` → `~/.config/opencode/skills/` |
| **Cursor** | project skills | `./bin/skills-sync` → `.cursor/skills/` symlinks |
| **Generic** | broker socket + token | loaded from `~/.config/agent-broker/env` into sandbox env |

### Global pi config (`~/.pi/agent/settings.json`)

If you use a **global** pi harness (not per-project `.pi/settings.json`), add this repo’s `skills/` directory with an **absolute path** in `~/.pi/agent/settings.json`:

```json
{ "skills": ["/path/to/subro/skills"] }
```

Or run `./bin/skills-sync --global-pi` / `./bin/agent pi` to merge it for you.

### Global OpenCode config (`~/.config/opencode/`)

OpenCode discovers skills at `~/.config/opencode/skills/<name>/SKILL.md` and stores sessions/auth under `~/.local/share/opencode`. The fake sandbox `HOME` would hide all of that without overrides.

`./bin/agent opencode` sets `OPENCODE_CONFIG_DIR`, `OPENCODE_DATA_DIR`, `OPENCODE_CACHE_DIR`, and `OPENCODE_STATE_DIR` to your real home paths. Run `./bin/skills-sync --global-opencode` to symlink broker skills into the global skills tree.

Secrets stay in `~/.config/agent-broker/env` (broker only), not in harness settings. Set `BROKER_ALLOWED_ROOTS` to cover your dev tree (comma-separated), including each project directory where you run `./bin/agent`.

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
./bin/agent pi            # pi coding agent
./bin/agent opencode      # OpenCode agent
```

### 1) Broker lifecycle

The broker is **on-demand**: `./bin/agent` starts it automatically if it is not already running. You do not need a separate terminal session.

For manual control:

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
./bin/broker-daemon status   # detects stale pid files and orphan sockets
```

If `status` reports a **stale socket** (file exists but process is dead), run `start` again — it removes the old socket before binding.

Logs go to `./.broker/log.txt`.

Debug without kernel sandbox: `SUBRO_NO_SANDBOX=1 ./bin/agent bash` (still uses scrubbed `env -i` and fake `HOME`).

To stop:

```bash
./bin/broker-daemon stop
```

### 2) Run a sandboxed agent command

The sandbox wrapper clears the environment (`env -i`), sets a minimal `PATH` that prefers `./interceptors`, and tries to enforce kernel sandboxing:

- macOS: `sandbox-exec` (Seatbelt)
- Linux: vendored `landlock-restrict` (build with `./bin/build-landlock-restrict`; falls back to unsandboxed if missing)

On Linux, `./bin/setup` tries to build the vendored helper automatically. Override with `SUBRO_LANDLOCK_RESTRICT=/path/to/landlock-restrict`. See [tools/landlock-restrict/README.md](tools/landlock-restrict/README.md).

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

