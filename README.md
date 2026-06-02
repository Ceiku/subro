# Kernel-sandboxed agent + privileged broker (UDS)

This repo provides a **local, high-performance tool-execution split**:

- A **sandboxed agent process** runs with a scrubbed environment and kernel-level filesystem restrictions.
- For sensitive tools (`mvn`, `curl` when it contains a placeholder key), lightweight **interceptors** forward the request to a **privileged broker** over a **Unix Domain Socket** at `/tmp/agent-broker.sock`.
- The broker executes the real tool with host privileges, injects secrets, **scrubs sensitive strings** from outputs, and returns safe results.

## File layout

```text
.
├── README.md
├── bin/
│   ├── agent-run
│   ├── install-interceptors
│   └── broker-daemon
├── broker/
│   ├── main.py
│   └── requirements.txt
└── interceptors/
    ├── mvn
    └── curl
```

## Quick start

### 1) Start the broker (privileged host process)

Seed the broker with:

- `PROD_API_KEY`: used to replace `X-PROD-KEY` in `curl` requests
- `BROKER_ALLOWED_ROOTS`: comma-separated list of directories the broker will accept as `workdir`
  - Recommended: set it to **this repo root** (and any other explicit workspaces you want)

From the repo root:

```bash
export PROD_API_KEY="example-prod-key-DO-NOT-USE"
export BROKER_ALLOWED_ROOTS="$(pwd)"

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

## Repo creation

This workspace can be initialized as `main` and published as a **private** GitHub repo via GitHub CLI:

```bash
git init -b main
gh repo create "$(basename "$(pwd)")" --private --source=. --remote=origin --push
```

