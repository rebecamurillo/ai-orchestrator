---
title: Rules
kind: page
audience: any
---
# Rules

- Handshake first (`connect`).
- Always preflight before creating a Run; resolve every `fail` line first.
- Discover template inputs from the API each time; templates evolve.
- A template save is the human's decision: validate, show the diff, wait for the go-ahead.
- One budget decision per Run, made by a human or from an explicit instruction — never
  invent or silently raise `budget_usd`.
- Poll at 5 s / 30 s; back off, never tighten.
- Choose signals from `admitted_signals`, never from assumption.
- A `blocked` park with a question you cannot answer from project context goes to the
  human, with the deep link.
- The token is a credential: never write it into files, logs, or command lines that get
  committed; read it from the environment at call time.
