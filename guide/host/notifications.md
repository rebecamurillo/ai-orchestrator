---
title: Notifications
kind: page
audience: host
---

Local agent on the host or the user only.

# Notifications

Set `NOTIFY_WEBHOOK_URL` in `.env` to be told when a Run needs you or ends. One POST is sent each time a Run enters `needs_you`, `done`, `failed` or `cancelled`; blank (the default) sends nothing. Delivery is best-effort: a webhook that is down is logged as `notify_failed` and never fails the Run.

- `NOTIFY_WEBHOOK_FORMAT=json` posts the structured event (run, project, repository, template, status, park kind, reason, step path, attempt, spend, time). `slack` posts a one-line `{"text": ...}` that Slack and Mattermost incoming webhooks accept.
- `NOTIFY_WEBHOOK_SECRET`, when set, adds `X-Orchestrator-Signature: sha256=<hex HMAC-SHA256 of the request body>` so the receiver can check the sender.
- `PUBLIC_BASE_URL` (for example `https://orchestrator.example.com`) adds a link to the Run; blank leaves it out.
