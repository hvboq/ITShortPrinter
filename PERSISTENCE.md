# Persistent storage note for Hermes / Docker

This repository should be treated as the canonical MoneyPrinterV2 working copy for this Hermes container:

```text
/opt/data/MoneyPrinterV2
```

Why: `/opt/data` is backed by the Docker volume configured in the Hermes container, while paths such as `/root/MoneyPrinterV2` are part of the container writable layer and can disappear if the container is recreated.

## Durable paths

```text
/opt/data/MoneyPrinterV2                         # canonical code working copy
/opt/data/skills                                 # Hermes skills
/opt/data/MoneyPrinterV2/docs/                   # project-local workflow backups
/opt/data/firefox-profiles/youtube               # copied logged-in Firefox profile for YouTube upload
```

## Important workflow backup

The project-specific Hermes skill is backed up here:

```text
docs/hermes-moneyprinterv2-workflow.md
```

The live Hermes skill path is normally:

```text
/opt/data/skills/software-development/moneyprinterv2-it-news-shorts/SKILL.md
```

## Do not store secrets

Do not commit or paste real API keys, cookies, tokens, browser profile contents, or passwords. Use environment variables such as `GOOGLE_API_KEY`, `GEMINI_API_KEY`, and `OPENAI_API_KEY`.
