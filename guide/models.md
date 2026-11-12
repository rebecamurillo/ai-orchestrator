---
title: Models a Run can use
kind: page
audience: any
---
# Models a Run can use

Ask the instance, never guess a model name: `GET /api/v1/harnesses/{name}/models`, or the MCP
tool `list_models`. The answer is `{harness, source, models, note, code, guide}`, and `source`
says where the list comes from.

- `litellm`: the instance's LiteLLM key's own `GET /v1/models`, read at most once per 60
  seconds. The note reads "the models this instance's LiteLLM key may use"; an empty list
  stays `litellm` with the note "LiteLLM lists no model for this instance's key".
- `configured`: the `local` harness answers `LOCAL_MODELS`, the aliases the host serves. No
  note.
- `none`: no LiteLLM gateway is configured, so the harness cannot list its models here. The
  note names the harness and carries `refusal-models-unlisted` with its page
  `errors/refusal-models-unlisted`. Ask the user for a model name the harness accepts; never
  invent one.

When a gateway is configured but cannot be read, the route answers 503 with
`refusal-models-gateway-unreachable` (page `errors/refusal-models-gateway-unreachable`). The
list is then unknown, and nothing is guessed in its place.

An unknown harness name is 404.

Changing the default models or LiteLLM's model list is local-only: it is done on the host
(`host/rules`), and no tool does it from here.
