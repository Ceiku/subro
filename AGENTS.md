# Agent instructions (subro)

Kernel-sandboxed agent runtime with broker-mediated tools.

## Start

```bash
./bin/agent bash      # sandboxed shell
./bin/agent pi        # pi coding agent
./bin/agent opencode  # OpenCode agent
```

Run from any project directory under `BROKER_ALLOWED_ROOTS` (not only this repo).

## Skills

Brokered CLI skills (use these — not raw `curl` for the same APIs):

- [`entur-departures`](skills/entur-departures/SKILL.md)

Run `./bin/skills-sync` after adding or changing skills.
`./bin/agent` runs skills-sync automatically when `skills/` changed.

See [README.md](README.md) for doctor, setup --check, apm, and cplt sandbox (default).
