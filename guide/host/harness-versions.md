---
title: Harness versions
kind: page
audience: host
---

Local agent on the host or the user only.

# Harness versions

**Pin the latest release.** When you set up or edit `.env` or `.env.example`, pin the latest
release of each of these, unless the user names a version. Look each one up, then write the
exact number, never the word `latest`, which the container refuses:

```bash
npm view @anthropic-ai/claude-code version                 # CLAUDE_CODE_VERSION
npm view @openai/codex version                             # CODEX_VERSION
npm view opencode-ai version                               # OPENCODE_VERSION
npm view @langfuse/opencode-observability-plugin version   # LANGFUSE_OPENCODE_PLUGIN_VERSION
```

`BMAD_VERSION` is outside this rule: it must equal the manifest in every target repository
(AD-16), so it moves only when those repositories do. An upgrade takes the pins from the
release's `release.env`, which can be older than the latest, so check them again after an upgrade.

The procedure and what to do if a release fails are in `host/runbooks`.
