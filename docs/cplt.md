# Optional cplt sandbox backend

[navikt/cplt](https://github.com/navikt/cplt) is an optional, **externally installed** kernel sandbox
(MIT license). subro stays on the default **native** backend (Seatbelt on macOS, Landlock on Linux)
unless you opt in.

The broker, interceptors, and skills are unchanged — only `bin/agent-run` chooses which kernel
sandbox wraps the agent process.

## When to use it

- Stronger env sanitization and outbound CONNECT proxy (domain/port filtering)
- Avoid maintaining local Seatbelt/Landlock policy yourself
- NAV/corporate laptops where cplt is already standard

Default `native` is fine for most subro development and CI.

## Install cplt (not bundled with subro)

```bash
brew install navikt/tap/cplt
# or: curl -fsSL https://raw.githubusercontent.com/navikt/cplt/main/install.sh | bash
cplt doctor
```

See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for licensing.

## Enable in subro

Add to `~/.config/agent-broker/env`:

```bash
SUBRO_SANDBOX=cplt
```

Then run agents as usual:

```bash
./bin/agent bash
./bin/agent pi
./bin/doctor
```

If `cplt` is not on `PATH`, or `cplt` exits non-zero, subro **falls back to native** and prints a warning.

`cplt` is resolved on the **host** `PATH` before subro scrubs `PATH` for the sandboxed child. If
`cplt` lives outside the usual PATH (e.g. `~/.local/bin`), ensure that directory is on your shell
`PATH`, or set an explicit binary:

```bash
SUBRO_CPLT_BIN=$HOME/.local/bin/cplt
```

## Disable kernel sandbox entirely

`SUBRO_NO_SANDBOX=1` skips both native and cplt kernel enforcement (env scrub + broker still apply):

```bash
SUBRO_NO_SANDBOX=1 ./bin/agent bash
```

## What subro passes to cplt

When `SUBRO_SANDBOX=cplt`, `agent-run`:

- Invokes `cplt --agent shell` (no nested native sandbox)
- Prepends interceptors via `PATH` (`--pass-env PATH`)
- Grants broker UDS access (`--allow-write` on the broker socket directory)
- Passes broker/harness vars: `BROKER_SOCK`, `BROKER_SOCKET_TOKEN`, `SUBRO_ROOT`, `PI_*`, `OPENCODE_*`

Privileged tools (`mvn`, broker skills) still run in the **host broker**, not inside cplt.

## Per-repo cplt policy (optional)

Copy `.cplt.toml.example` to `.cplt.toml` if you need extra project permissions (localhost ports,
private registry reads, etc.). Broker socket access is handled by `agent-run` flags — you do not need
to duplicate that in TOML.

```bash
cp .cplt.toml.example .cplt.toml
# edit, then if using [propose] entries:
cplt trust accept --all
```

## Switch back to native

Remove or comment out `SUBRO_SANDBOX=cplt` in the broker env file (default is `native`).
