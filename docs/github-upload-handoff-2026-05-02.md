# GitHub upload handoff — 2026-05-02

## Current intent

User wants to upload the customized MoneyPrinterV2 Shorts project to GitHub.

Original upstream repository provided by user:

- https://github.com/FujiwaraChoki/MoneyPrinterV2

User explicitly requested:

1. Review original repository contents.
2. Confirm license.
3. Update `README.md` to mention the original repository and clearly attribute the source.
4. Prepare to upload the customized Shorts project to GitHub.

## Verified upstream/license facts

Local repo remote currently points to upstream:

```text
origin https://github.com/FujiwaraChoki/MoneyPrinterV2
```

Tracked upstream files include:

```text
LICENSE
README.md
```

The upstream `LICENSE` is:

```text
GNU AFFERO GENERAL PUBLIC LICENSE
Version 3, 19 November 2007
```

The upstream README states:

```text
MoneyPrinterV2 is licensed under `Affero General Public License v3.0`.
```

Conclusion: upstream license is **GNU Affero General Public License v3.0 (AGPL-3.0)**.

## Changes already made for attribution/license compliance

`README.md` was updated at the top:

- Title changed to `MoneyPrinter V2 — Korean IT News Shorts Automation Fork`
- Added fork / attribution notice:
  - This repo is a customized fork of `FujiwaraChoki/MoneyPrinterV2`
  - Original upstream URL: https://github.com/FujiwaraChoki/MoneyPrinterV2
  - Upstream license: GNU Affero General Public License v3.0 (AGPL-3.0)

`README.md` license section was updated:

- Section renamed to `License and upstream attribution`
- Explicitly states this fork is based on the original upstream repo
- States this customized fork preserves AGPL-3.0
- Notes AGPL-3.0 network-service source-code availability obligations

`.gitignore` was updated:

- Keeps `config.json`, `.env`, `.env.*`, `.mp/`, `venv/`, `Songs/` ignored
- Allows `.env.example`
- Adds local font exclusion:
  - `fonts/*.ttf`
  - `fonts/*.ttc`
  - `fonts/*.otf`
  - `!fonts/.gitkeep`

Reason: `fonts/malgun.ttf` and `fonts/malgunbd.ttf` are likely Windows Malgun Gothic files and should not be redistributed to GitHub.

## GitHub authentication status

Checked locations:

- `GITHUB_TOKEN` environment variable
- `~/.hermes/.env`
- `~/.git-credentials`

Result at time of handoff:

```text
GitHub token presence check: missing
Credential source: none
```

Therefore GitHub repo creation/push is currently blocked until the user provides a token.

Do **not** print or store the token value. Only test it with boolean/API-success output.

## Current git status summary

Working tree has many uncommitted changes for the customized project. Important modified/untracked files include:

Modified:

```text
.gitignore
README.md
config.example.json
requirements.txt
src/classes/Tts.py
src/classes/YouTube.py
src/config.py
src/constants.py
src/main.py
```

Untracked notable files/directories:

```text
.env.example
PERSISTENCE.md
docs/hermes-moneyprinterv2-workflow.md
docs/restart-handoff-env-and-gemini.md
docs/session-checkpoint-2026-04-26.md
docs/session-progress-*.md
scripts/fix_rank1_metadata.py
scripts/generate_top5_shorts.py
scripts/publish_draft_public_shorts.py
scripts/publish_draft_shorts.py
scripts/set_env_keys.py
scripts/upload_top5_public_shorts.py
scripts/upload_top5_shorts.py
scripts/verify_recent_public_shorts.py
src/gemini_image.py
src/news/
tests/test_*.py
```

Untracked local font files existed earlier:

```text
fonts/malgun.ttf
fonts/malgunbd.ttf
```

They are now ignored by `.gitignore` and should not be committed.

## Pre-push safety checks to run after restart/token

From `/opt/data/MoneyPrinterV2`:

```bash
# Verify token without printing it
python3 - <<'PY'
import os, json, urllib.request, re, sys
from pathlib import Path
secret=os.environ.get('GITHUB_TOKEN','').strip()
if not secret:
    env=Path.home()/'.hermes/.env'
    if env.exists():
        for line in env.read_text(errors='ignore').splitlines():
            if line.startswith('GITHUB_TOKEN='):
                secret=line.split('=',1)[1].strip(); break
print('token_present=', bool(secret))
if secret:
    req=urllib.request.Request('https://api.github.com/user', headers={'Authorization':'Bearer '+secret, 'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'hermes-agent'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data=json.load(r)
    print('github_api_ok=True')
    print('login=', data.get('login'))
PY

# Confirm ignored sensitive/generated files
git check-ignore -v config.json .env .mp/foo.mp4 fonts/malgun.ttf fonts/malgunbd.ttf || true

# Confirm no real secrets are staged/tracked; search output must be reviewed manually
rg -n --hidden --glob '!.git/**' --glob '!venv/**' --glob '!.mp/**' --glob '!config.json' --glob '!.env*' 'AIza|ghp_|github_pat_|sk-[A-Za-z0-9]|OPENAI_API_KEY=.*[A-Za-z0-9]{10,}|GOOGLE_API_KEY=.*[A-Za-z0-9_-]{10,}|GEMINI_API_KEY=.*[A-Za-z0-9_-]{10,}' . || true

# Syntax smoke checks
PYTHONPATH=src venv/bin/python -m py_compile \
  src/config.py \
  src/gemini_image.py \
  src/news/fetcher.py \
  src/news/ranker.py \
  src/news/shorts.py \
  src/news/collector.py \
  src/classes/Tts.py \
  src/classes/YouTube.py \
  scripts/generate_top5_shorts.py \
  scripts/upload_top5_public_shorts.py \
  scripts/verify_recent_public_shorts.py
```

If `rg` is unavailable, use `grep -R` carefully or `search_files` from Hermes. Do not print secret values.

## Recommended upload approach

Do not push to the upstream `origin` (`FujiwaraChoki/MoneyPrinterV2`).

Create a new repo under the authenticated user's GitHub account, probably private by default unless the user explicitly asks public.

Suggested repo name:

```text
moneyprinterv2-korean-it-shorts
```

Recommended remotes:

```text
origin   = user's new GitHub repo
upstream = https://github.com/FujiwaraChoki/MoneyPrinterV2
```

Because current `origin` is upstream, after creating the new repo:

```bash
git remote rename origin upstream
# then add user's repo as origin
# git remote add origin https://github.com/<USER>/moneyprinterv2-korean-it-shorts.git
```

If creating repo via GitHub API using token:

```bash
python3 - <<'PY'
# Use token from env; do not print it.
# POST https://api.github.com/user/repos
# JSON: {"name":"moneyprinterv2-korean-it-shorts", "private": true, "description":"Korean IT-news Shorts automation fork of FujiwaraChoki/MoneyPrinterV2", "auto_init": false}
PY
```

Then commit and push:

```bash
git add .
git status --short
# ensure ignored files like config.json, .env, .mp, fonts/*.ttf are not staged

git commit -m "Customize MoneyPrinterV2 for Korean IT-news Shorts automation"
git push -u origin main
```

If token must be used for HTTPS push and `gh` is not installed, either:

1. configure credential helper without printing token:

```bash
git config --global credential.helper store
# write credentials only if user explicitly permits persistent local storage
```

or

2. use a one-time token-embedded remote URL but avoid logging it. Prefer using `git credential approve` or `GIT_ASKPASS` script to avoid token appearing in process logs.

## Current upload attempt status — updated 2026-05-02

Final pre-push checks completed:

- `config.json`, `.env`, `.mp/`, `venv/`, `Songs/`, and `fonts/malgun*.ttf` are ignored.
- No unignored files larger than 5 MB were found.
- Suspicious filename scan was clear.
- Content scan for GitHub tokens, Google API keys, OpenAI keys, and private-key blocks was clear.
- Python syntax smoke check with system `python3` passed for the modified modules/scripts.

Local commit created successfully:

```text
2c2ca2d Customize MoneyPrinterV2 for Korean IT-news Shorts automation
```

GitHub token status:

- Token is visible through Docker PID 1 environment as `GITHUB_TOKEN`.
- GitHub API authentication succeeds as account `hvboq`.
- However, creating a new repository failed with HTTP 403:

```text
Resource not accessible by personal access token
```

Repository lookup for `hvboq/moneyprinterv2-korean-it-shorts` returned 404, so that repo was not accessible/created at this time.

Next step to finish upload:

1. Either provide a token with permission to create repositories (classic PAT with `repo` scope is the simplest), or manually create an empty private GitHub repo named `moneyprinterv2-korean-it-shorts` under `hvboq`.
2. Then set the new repo as `origin` while preserving upstream:

```bash
git remote rename origin upstream  # if not already renamed
# git remote add origin https://github.com/hvboq/moneyprinterv2-korean-it-shorts.git
```

3. Push local commit `2c2ca2d` to the new repo.

## Cautions

- Do not commit `.mp/` outputs, generated MP4/PNG/WAV/SRT/JSON manifests, YouTube screenshots, browser profiles, cookies, `config.json`, `.env`, or any token/key material.
- Do not commit proprietary font files (`fonts/malgun.ttf`, `fonts/malgunbd.ttf`).
- Keep AGPL-3.0 LICENSE intact.
- README attribution to upstream is already added and should be kept.
- The repo currently has scheduled cron jobs in Hermes, but cron definitions are outside this git repo and do not need GitHub commit.
