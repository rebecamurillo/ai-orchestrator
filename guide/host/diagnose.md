---
title: Diagnose, and filing a bug
kind: procedure
audience: host
---

Local agent on the host or the user only.

# Diagnose, and filing a bug

```bash
./install.sh diagnose
```

Writes `diagnostics/<UTC timestamp>.md`: the versions (`/api/v1/version`,
`VERSION`), `docker compose ps`, the last 200 lines of `docker compose logs`, and `.env` with
every value masked except the non-secret kinds (ports, crons, versions, directories, flags).
Secrets are masked by name and the logs are filtered for token-shaped strings. It is still a
log dump: read it before sending it, because a log line carries whatever a target repository
printed.

Then compose the report. Title: one line, the symptom, not the guess. Body:

```
**What happened** — what the user did, and what the instance did instead.
**Expected** — in one sentence.
**Versions** — app, VERSION, bmad, harness CLIs (from the diagnostics file).
**Reproduce** — the smallest sequence, by command and by API call.
**Evidence** — the relevant log lines, and the Run id / step path if there is one.
**Diagnostics** — diagnostics/<timestamp>.md, attached.
```

Transport:

```bash
gh auth status && gh issue create --repo rebecamurillo/ai-orchestrator \
  --title "<title>" --body-file <file>
```

**The repository is private today.** If `gh auth status` fails, or the user has no access to
it, say so plainly: write the report to `issue.md` beside the diagnostics, hand them the
prefilled URL `https://github.com/rebecamurillo/ai-orchestrator/issues/new`, and tell them to
paste it and attach the diagnostics file themselves. Do not attach a diagnostics file to
anything the user has not read.
