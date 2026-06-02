---
name: entur-departures
description: Read-only departure board lookups for three Oslo stops via Entur (public API).
---

# Entur departures (showcase skill)

Use this when the user asks for **departures**, **next trains/metro**, or **stop boards** in Oslo.

## Tool

Run the local CLI (do **not** call `curl` against Entur yourself):

```bash
entur-departures <stop-alias> [count]
```

### Allowed stops (only these)

| Alias | Stop |
|-------|------|
| `jernbanetorget` | Jernbanetorget |
| `nationaltheatret` | Nationaltheatret |
| `oslo-s` | Oslo S |

`count` is optional (default `5`, max `10`).

### Examples

```bash
entur-departures jernbanetorget
entur-departures nationaltheatret 8
entur-departures oslo-s 5
```

Output is JSON with `departures[]` (`time`, `destination`, `line`, `mode`).

## Security notes

- Lookups only — no writes, no arbitrary URLs, no custom GraphQL from the agent.
- The broker enforces the stop allowlist and a fixed query shape.
- No API key is required for this public Entur endpoint; the broker sets `ET-Client-Name`.
