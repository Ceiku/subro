# Pre-public repository audit

**Date:** 2026-06-05  
**Repo:** `Ceiku/subro` (currently **private**)  
**Verdict:** Safe to make public **after** optional history scrub (see below). No credentials found in tree or history.

## Current tree (HEAD) — PASS

| Check | Result |
|-------|--------|
| API keys / tokens (`ghp_`, `gho_`, `sk-`, etc.) | None in tracked files |
| `.env`, `.npmrc`, `.netrc`, `.pypirc` | Not tracked; listed in `.gitignore` |
| Broker logs / PID (`.broker/`) | Not tracked |
| `broker/.venv/` | Not tracked |
| Local skill symlinks (`.cursor/skills`, etc.) | Not tracked |
| Hardcoded secrets in code | Only placeholders (`X-PROD-KEY`) and scrub patterns |

## Git history — MINOR ISSUES

| Item | Severity | Status |
|------|----------|--------|
| `subro.lock.json` contained `a machine-specific path...` | Low (path metadata) | **Fixed in HEAD**; still in old commits |
| `.agent-skills/demo.py` (harmless test script) | Low | Removed in `b62d1d3` but **still in history** (`55dbf53`) |
| Commit author email `daniels@aboveit.no` | Info | **Permanent in git history** unless rewritten |
| `Co-authored-by: Cursor` on one commit | Info | Not sensitive |

**No secrets** (`PROD_API_KEY`, `BROKER_SOCKET_TOKEN`, real tokens) were ever committed.

## `.gitignore` coverage — PASS

Ignores: `.broker/`, `.venv`, `.agent-*`, harness symlinks, `.env*`, npm/pypi/netrc files.

## Recommended before `gh repo edit --visibility public`

### 1. Optional: scrub history (recommended)

Removes home-directory path from lockfile history and test `demo.py` blob:

```bash
# Requires: brew install git-filter-repo
# Back up first: git clone --mirror . ../subro-backup.git

# Remove accidental test artifact from history
git filter-repo --path .agent-skills/demo.py --invert-paths --force

# Scrub home-directory prefix from lockfile (only appears in subro.lock.json)
printf 'literal:==>\n' > /tmp/subro-scrub.txt
git filter-repo --replace-text /tmp/subro-scrub.txt --force

git push --force-with-lease origin main
```

Only run if you are the sole consumer of this repo or have coordinated with collaborators.

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
