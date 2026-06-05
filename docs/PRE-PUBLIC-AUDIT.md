# Pre-public repository audit

**Date:** 2026-06-05  
**Repo:** `Ceiku/subro` (currently **private**)  
**Verdict:** Safe to make public. No credentials found in tree or history; history scrub completed.

## Current tree (HEAD) — PASS

| Check | Result |
|-------|--------|
| API keys / tokens (`ghp_`, `gho_`, `sk-`, etc.) | None in tracked files |
| `.env`, `.npmrc`, `.netrc`, `.pypirc` | Not tracked; listed in `.gitignore` |
| Broker logs / PID (`.broker/`) | Not tracked |
| `broker/.venv/` | Not tracked |
| Local skill symlinks (`.cursor/skills`, etc.) | Not tracked |
| Hardcoded secrets in code | Only placeholders (`X-PROD-KEY`) and scrub patterns |

## Git history — CLEAN (post-scrub)

| Item | Severity | Status |
|------|----------|--------|
| `subro.lock.json` contained machine-specific absolute paths | Low (path metadata) | **Scrubbed from history** (`git filter-repo`) |
| `.agent-skills/demo.py` (harmless test script) | Low | **Removed from history** (`git filter-repo`) |
| Commit author email `daniels@aboveit.no` | Info | **Permanent in git history** unless rewritten |
| `Co-authored-by: Cursor` on one commit | Info | Not sensitive |

**No secrets** (`PROD_API_KEY`, `BROKER_SOCKET_TOKEN`, real tokens) were ever committed.

## `.gitignore` coverage — PASS

Ignores: `.broker/`, `.venv`, `.agent-*`, harness symlinks, `.env*`, npm/pypi/netrc files.

## Recommended before `gh repo edit --visibility public`

### 1. History scrub — DONE (2026-06-05)

Removed `.agent-skills/demo.py` and rewrote absolute lockfile paths to relative via `git filter-repo`, then force-pushed `main`.

### 2. Rotate nothing required

No leaked credentials were found. Your **local** `~/.config/agent-broker/env` was never committed.

### 3. Regenerate lockfile after clone (optional)

```bash
./bin/apm install entur-departures
```

Now stores **relative** `source` paths only.

### 4. Make repo public

```bash
gh repo edit Ceiku/subro --visibility public
```

### 5. Post-public hygiene

- Do not commit `subro.lock.json` with machine-specific absolute paths (fixed in `apm.py`)
- Tag releases for FSL DOSP dates: `git tag v0.1.0 && git push origin v0.1.0`
- Add GitHub **secret scanning** (enabled by default on public repos)

## Local files to keep out of git (verify)

```bash
git status --ignored | head -20
```

Expected ignored: `.env`, `.broker/`, `broker/.venv/`, `.agent-skills/`
