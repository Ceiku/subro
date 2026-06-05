# Optional cplt sandbox backend

[Ceiku/cplt](https://github.com/Ceiku/cplt) (fork of [navikt/cplt](https://github.com/navikt/cplt)) is the **default**
kernel sandbox (MIT license, not bundled). subro uses native Seatbelt/Landlock only when cplt is
unavailable or you set `SUBRO_SANDBOX=native`.

The broker, interceptors, and skills are unchanged — only `bin/agent-run` chooses which kernel sandbox
wraps the agent process.

## Install cplt (required for default sandbox)

```bash
curl -fsSL https://raw.githubusercontent.com/Ceiku/cplt/main/install.sh | bash
cplt doctor
cplt trust accept --all   # approve repo .cplt.toml once
```

See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for licensing.

## Opt out to native

Add to `~/.config/agent-broker/env`:

```bash
SUBRO_SANDBOX=native
```

If `cplt` is not on `PATH`, or `cplt` exits non-zero, subro **falls back to native** and prints a warning.

`cplt` is resolved on the **host** `PATH` before subro scrubs `PATH` for the sandboxed child. If
`cplt` lives outside the usual PATH (e.g. `~/.local/bin`), ensure that directory is on your shell
`PATH`, or set an explicit binary:

```bash
SUBRO_CPLT_BIN=$HOME/.local/bin/cplt
```

`./bin/doctor` and `./bin/setup --check` report the resolved cplt path when using the default backend.

## Disable kernel sandbox entirely

`SUBRO_NO_SANDBOX=1` skips both cplt and native kernel enforcement (env scrub + broker still apply):

```bash
SUBRO_NO_SANDBOX=1 ./bin/agent bash
```

## What subro passes to cplt

When the default backend is active, `agent-run` maps harnesses to the correct cplt agent (do not use
`--agent shell` for `pi` — it cannot exec bare command names):

| subro command | cplt invocation |
|---------------|-----------------|
| `pi …` | `cplt --agent pi …` + `--allow-localhost-any` |
| `opencode …` | `cplt --agent opencode …` + `--allow-localhost-any` |
| `bash -lc 'cmd'` | `cplt --agent shell -- -c 'cmd'` |
| `bash` (interactive) | `cplt --agent shell` |

Also:

- Prepends interceptors via `PATH` (`--pass-env PATH`)
- Grants broker UDS access (`--allow-write` on the broker socket directory and socket path)
- Passes broker/harness vars: `BROKER_SOCK`, `BROKER_SOCKET_TOKEN`, `SUBRO_ROOT`, `PI_*`, `OPENCODE_*`

Disable localhost allowlist: `SUBRO_CPLT_NO_LOCALHOST=1` (pi TUI/print mode will likely break).

## Broker UDS under cplt

Broker interceptors connect via Unix domain socket (`BROKER_SOCK`). subro passes both
`--allow-write` on the socket **directory** and the socket **path** (matching native Seatbelt's
literal socket rule).

If `entur-departures` still fails with `PermissionError` on `s.connect()` under cplt, verify
`./bin/doctor` steps 8–9 or use `SUBRO_SANDBOX=native`.

## Known upstream: cplt exit code

cplt may return **exit 0** when the sandboxed inner command fails. subro only falls back to
native when the combined exit code is non-zero. If you see success without broker output, verify
with `./bin/agent-run bash -lc 'entur-departures --help'` or use `SUBRO_SANDBOX=native`.

Privileged tools (`mvn`, broker skills) still run in the **host broker**, not inside cplt.

## Per-repo cplt policy (optional)

Copy [`.cplt.toml.example`](../.cplt.toml.example) to `.cplt.toml` if you need extra project
permissions (localhost ports, private registry reads, etc.). Broker socket access is handled by
`agent-run` flags — you do not need to duplicate that in TOML.

```bash
cp .cplt.toml.example .cplt.toml
# edit, then if using [propose] entries:
cplt trust accept --all
```
