---
title: Drive an initiative for the operator
kind: procedure
audience: any
---
# Drive an initiative for the operator

This procedure is for the operator's own agent, connected to this instance over MCP. It creates
an initiative and then speaks for her in its conversation steps: the intake, product, UX and
tech personas run inside the instance and do the step work; you answer them from what she said
and what you know of her application, and you bring her in when the answer is hers to give. The
orchestrator still owns the sequence, the step files, the gate, the merge and the build. You
never write a step file, a spec file or a branch yourself.

The package format, the step words and the gate are `initiatives/package`. The handshake and
the connection values are `connect`.

## 1. Before the first call

1. `version`, and act on `bootstrap_contract` as `connect` says.
2. `list_projects`: pick the Project she named. Never pick one she did not name.
3. `read_package` for it: an initiative needs an installed package. No package is a stop:
   tell her, and point her to `initiatives/package`.
4. The Project's run defaults, read from `list_projects`: `default_budget_usd` must be set.
   A null budget is a stop: ask her for the number and set it with `set_run_defaults`,
   carrying her number unchanged. Never invent, round or raise a budget.

The sequence of workflows is the package's, fixed per Project. There is no choice to make per
initiative.

## 2. Create

`create_initiative` with `{project_id, name, first_message}`. `name` becomes the slug of the
hub branch `spec/{slug}`. `first_message` is the first turn of the first conversation step:
write it from her request, in her words where she gave them, with the context you hold that
the persona cannot read (what the application already does, what she ruled out). Keep the
returned `id`; tell her the initiative exists and give her its page, `<web base>/initiatives/{id}`,
the link every stop below hands her.

## 3. The loop

1. `wait_initiative` with the `since` of the previous answer (none the first time). It answers
   when the initiative moved, or with `changed: false` when the wait ran out; call it again.
2. Read `attention`:
   - `queued` or `answering`: the persona is working. Wait again.
   - `your_turn`: the step waits for an answer. `get_session` with the answer's `run_id`,
     read the persona's last reply in full, and answer it with `post_session_message`.
   - `blocked`: stop and go to § 4.
   - none, with `initiative_status` `running`: an automatic step (gate, merge, build) runs.
     Wait again.
3. A failed turn (`last_turn_status: failed`): `retry_session` once. A second failure goes to
   her with the session's failure reason.

Every message you send is stored as `[the operator's agent] <your text>`: the transcript, the
step log and the board show it came from you, not from her keyboard. Answer only what you can
ground in what she said or in the application as it is. Say so when you are inferring.

## 4. When to stop and ask her

Stop the loop and bring her the persona's question verbatim, with the initiative's link, when it
is:

- a business scope or priority choice you cannot ground in what she said;
- any budget, or anything that spends beyond the Run's budget;
- a failed gate round (the gate's `fail` word started a new round): she reads the gate's
  reasons before anyone answers them;
- a blocked step (`attention: blocked`, or a `park_reason` you cannot act on);
- a reopen: she reopens a step on the board, and no tool does it;
- anything irreversible: `cancel_initiative`, or `start_next`, which leaves the open step
  unclosed, only on her explicit word.

Once she answers, carry her answer into the session as she gave it, and resume the loop.

## 5. The close word

A conversation step closes on the operator's close word, recognised by the persona, together
with the step file's done word (`initiatives/package`, § The step file and its words). You may
send the close word on her behalf when the step's files hold what she asked for: read the
persona's last reply, which says what the file now holds, and the step's `files` and
`files_state` in `get_initiative` first; the detail names the files, not their text. Under the prefix it
counts as hers, recorded as said by her agent. Each time, tell her which step you closed and
what its file holds. A step that does not close shows why in its `park_reason`; answer that,
or bring it to her.

## 6. After the spec

When the gate passes, the package merges the spec and starts the build workflow. From there
the build is an ordinary Run: supervise it with `initiatives/run`, and answer its parks by the
table in `initiatives/autonomy`. `budget` and `checkpoint` parks stay hers.
