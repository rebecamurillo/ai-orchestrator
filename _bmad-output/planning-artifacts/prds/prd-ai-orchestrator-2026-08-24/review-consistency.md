# Adversarial consistency review — AI Orchestrator PRD

**Scope:** internal contradictions and traceability gaps in `prd.md` + `addendum.md`, measured against upstream `_bmad-output/forge/agent-workflow-os/forged-idea.md`.
**Method:** full read of all three; every FR/NFR/SEC/C-n/Q-n/§N identifier enumerated and every cross-reference resolved against its target.
**Reviewed:** 2026-08-25. Line numbers are as-of that read.

**Verdict:** the PRD is internally coherent at the level of prose, and incoherent at the level of *obligations*. Five upstream locked/hardening items are silently softened or reversed, and four requirement pairs cannot both be satisfied as written.

Counts: **9 critical · 11 high · 12 medium · 6 low**

---

## 1. FR numbering integrity

### 1.1 Full enumeration, in document order

`prd.md` defines 71 requirement ids across §6:

FR-1, 2, 3, **3a**, 4, **4a**, 5 (F1, L107–122) · FR-6, 7, **7a**, **7b**, 8, 9, 10, 11, **11a**, **11b**, **11c**, 12, **12a** (F2, L125–145) · FR-**12b**, **12c**, **12d**, **12e**, 13, 14, 15, 16, 17, 18, 19, **19a**, **19b**, **19c** (F3, L148–161) · FR-20–26 (F4, L164–170) · FR-27, 28, **28a**, **28b**, 29, 30, 31, 32 (F5, L173–180) · FR-33–37 (F6, L183–187) · FR-38, 39, 40, **40a**, 41, 42 (F7, L190–195) · FR-43, 44, 45, 46, **50, 51, 52** (F8, L198–204) · FR-47, 48, 49 (F9, L207–209).

**No duplicate ids. No missing integers — 1 through 52 are all defined exactly once.**

### 1.2 [MEDIUM] The base sequence is not monotonic: 47–49 are defined *after* 50–52

`prd.md:198–204` (F8 Observability) runs `FR-43, 44, 45, 46, 50, 51, 52`; `prd.md:207–209` (F9 Test environment) then defines `FR-47, 48, 49`. A reader scanning in order hits an apparent 47–49 gap at L201→202 and an apparent backward jump at L204→207. FR-50/51/52 were evidently appended late (they are the §12.1 instruments, `prd.md:290–292`) and dropped into the nearest thematic section rather than at the end of the sequence. Either renumber F9 to 47–49 → 44a–44c style suffixes, or move FR-50–52 after FR-49.

### 1.3 [MEDIUM] Requirements defined but never referenced by anything

The following FRs appear exactly once, at their own definition, and are not cited by any other FR, NFR, SEC, C-n, Q-n, §-prose, or by `addendum.md`. Several of them are load-bearing, which makes the silence significant rather than cosmetic:

- **FR-27** (gate-strength declaration) — this is forge hardening item #3. Nothing else in the PRD consumes it. No FR requires gate strength to be *stored*, *displayed* (FR-12 read-only viewing does not mention it), or *reported to GitHub* (FR-41 says "gate status", not gate strength). The hardening item is declared and then orphaned. See §4.4.
- **FR-29** (Playwright E2E as baseline oracle) — never cited, despite being the thing §3's admission criterion (`prd.md:52`), FR-3a (`prd.md:119`), FR-28b (`prd.md:176`) and §5 step 11 (`prd.md:87`) all depend on. FR-3a even cites *FR-28* where FR-29 is the substantive target.
- **FR-28a** (checkpoint validation) — never cited; §5 step 5 (`prd.md:81`) describes it without an id.
- **FR-47** and **FR-49** — FR-49 (teardown) is cited nowhere and provisions nothing (see §5.1).
- Also unreferenced: FR-1, 4, 4a, 5, 6, 7, 7a, 7b, 8, 11, 11b, 11c, 12, 12a, 12b, 12c, 12d, 12e, 13, 14, 15, 16, 17, 18, 20, 25, 26, 32, 34, 35, 36, 37, 38, 39, 40, 40a, 41, 42, 45, 46.

Isolated definitions are normal for leaf requirements; they are a defect for FR-27 and FR-29, which the document's own arguments rest on.

### 1.4 [LOW] No FR id is referenced that does not exist

Checked every `FR-nn` token in both files. All resolve. `addendum.md` cites FR-9, 10, 17, 21, 22, 23, 24, 28b, 30, 31, 33, 43, 44, 48, NFR-2/3/4, SEC-1/3/6/9, C-1/3/4/5 — all defined.

---

## 2. Cross-reference correctness

### 2.1 [MEDIUM] `prd.md:119` (FR-3a) cites FR-28 where FR-29 is the actual obligation

> "A skipped oracle is an absent oracle (FR-28) and must render as `unvalidated`."

FR-28 (`prd.md:174`) says a step with no oracle renders `unvalidated` — so the citation is *technically* accurate. But the requirement FR-3a is quietly overriding is **FR-29** (`prd.md:177`), which states Playwright E2E runs "before any PR is offered for human review" with no exception clause. Citing the permissive rule and not the mandatory one hides the conflict. See §3.4.

### 2.2 [MEDIUM] `prd.md:219` (NFR-5) bounds itself by a constraint the PRD claims is resolved

> "**NFR-5** A workflow parked for 30 days resumes correctly. *(Bounded by the session-retention constraint in §9.)*"

The §9 target is **C-4** (`prd.md:248`), whose *mitigation* is a Postgres-backed session store — and whose last sentence reads "This resolves the container-local state risk carried over from the forge." If C-4 is mitigated, the 30-day local-file retention is not a bound on anything and NFR-5 should not cite it. If it is not mitigated, C-4's closing sentence is wrong. One of the two is stale.

### 2.3 [MEDIUM] `prd.md:153` (FR-14) and `prd.md:219` (NFR-5) disagree on park duration

FR-14: park "**indefinitely** — days or weeks". NFR-5: "parked for 30 days resumes correctly." Indefinite and 30 days are not the same commitment, and no FR reconciles them. Given C-4's 30-day retention this is likely a real ceiling that FR-14 overstates.

### 2.4 [MEDIUM] `prd.md:268` (Q9) cites "FR-11a–c" for a claim only FR-11c makes

Q9 "Are workflows dynamic? — Resolved — dynamic *instantiation* from authored templates; **not** dynamic structure. See FR-11a–c." FR-11a is a template inventory; **FR-11b is about the intake variant branch and says nothing about dynamism**. Only FR-11c (`prd.md:143`) states the claim. Range citation over-reaches.

### 2.5 [LOW] `prd.md:260` (Q1) says "G1 signature"; §5 splits the gate into G1a/G1b

Q1 asks "Which artifact carries the human's **G1** signature?" There is no gate named G1 in the §5 table (`prd.md:91–96`) — only G1a and G1b. The resolution text does name `epics.md`/G1b correctly, so this is terminology drift, not a wrong answer. But see §4.1, where the answer itself contradicts upstream.

### 2.6 [LOW] `addendum.md:109` and `addendum.md:137` cite "§12" with no document qualifier

The addendum has no §12; the target is `prd.md` §12. Both files use a bare `§N` convention, so a cross-document `§` reference is ambiguous.

### 2.7 [LOW] `addendum.md:96` cites FR-48 as governing "concurrency decisions" — FR-48 forbids concurrency

> "**Sizing:** roughly 1 GiB RAM / 5 GiB disk / 1 CPU per concurrent agent. Relevant to FR-48 concurrency decisions."

FR-48 (`prd.md:208`) is the *anti*-concurrency enforcement requirement. Per-concurrent-agent sizing is only actionable in a world FR-47/48 rule out for the PoC.

### 2.8 [HIGH] `addendum.md` §B contradicts itself on whether a resuming host must match cwd

- `addendum.md:43`: "**Resume (FR-23):** `claude -p --resume "$id" "message"`. Recent versions search all projects, **so cwd need not match**."
- `addendum.md:46`: "`SessionKey.projectKey` encodes the working directory, so **a resuming host must match cwd** or pin the project-dir name."

Both describe resume. The same paragraph then concludes "drive the SDK with a Postgres-backed store, **not the bare CLI**" — meaning L46 is the governing statement and L43's reassurance does not apply on the chosen path. As written, an implementer reading L43 will build something that breaks. This is not cosmetic: the cwd constraint is what makes §5.4 below a real defect.

---

## 3. Internal contradictions

### 3.1 [CRITICAL] FR-47/FR-48 forbid the concurrency that §1's value proposition is built on

- `prd.md:16` (§1): "It moves a senior engineer from *writing* implementations to *specifying and verifying* them, **across several pipelines running in parallel**."
- `prd.md:207` (FR-47): "Serialize execution per worktree. No concurrent runs against the same repository branch. **The PoC iterates through epics sequentially.**"
- `prd.md:208` (FR-48): "reject or queue a second run rather than allowing two to share a worktree **or a database**."
- `prd.md:266` (Q7): "Resolved — **no concurrency in the PoC**; serialized per worktree."
- `prd.md:215` (NFR-1): "Single Docker container for the PoC: orchestrator, tooling ..., and **a Postgres** it can reach."

Three separate escalations, each broader than the last:

1. FR-47 sentence 1 serializes *per worktree* — compatible with parallel pipelines across projects.
2. FR-47 sentence 2 — "the PoC iterates through **epics** sequentially" — is global, not per-worktree, and eliminates cross-project parallelism outright. The parenthetical that follows ("*this is narrower than serializing per project — but the PoC does not exploit that*") **confirms** the narrower scope is deliberately not used.
3. FR-48's "or a database" is fatal on its own: NFR-1 provisions exactly **one** Postgres, so no two runs may ever execute concurrently anywhere in the system.

§1's "several pipelines running in parallel" and Q7's "no concurrency in the PoC" cannot both be true. The §6 blockquote (`prd.md:211`) defends the trade honestly but never notices it has priced out the headline claim. **This is also an upstream reversal — see §4.3.**

**Fix:** either (a) state plainly in §1 that pipeline parallelism is v2 and the PoC is serial, or (b) scope FR-48's database clause to the *E2E* database, add a schema-per-run requirement (forge hardening #4's first option), and delete FR-47 sentence 2.

### 3.2 [CRITICAL] The rework cap has no terminal state — it escalates to the human it is escaping from

- `prd.md:158` (FR-19): "Cap rework cycles per story (default 2), **then escalate to a human**."
- `prd.md:160` (FR-19b): "Review loops count against the FR-19 cap."
- `prd.md:186` (FR-36): "Approve or reject an epic at final QA, with rejection creating a fix cycle **bounded by FR-19**."

The only human in the loop at that point is the G3 reviewer whose rejection consumed the cycles. FR-19's escape hatch routes back to its own trigger. **No requirement defines what the system does when the cap is exhausted**: abandon the story? mark it terminally failed? hand to FR-18 cancel-and-rollback? open the PR anyway with `unvalidated` status? FR-33 (`prd.md:183`) enumerates only two inbox item types, neither of which is "story exhausted its rework budget."

Compounding it: **FR-19 caps per *story*, FR-19a re-runs "the epic and its stories"** (`prd.md:159`). One epic-level rejection therefore burns a cycle from every story in the epic, including stories that were never at fault. Two epic rejections exhaust the entire epic.

### 3.3 [HIGH] §2's rework warning threshold is unreachable by construction

`prd.md:35` (§2 supporting metrics): "Rework cycles per story | tracked; **≥3 is a warning sign**."
`prd.md:158` (FR-19): cap "default 2".

A story cannot reach 3 rework cycles — FR-19 stops it at 2. The warning threshold can never fire. Either the metric threshold is stale (should be "≥2 = at cap") or FR-19's default should be 3+.

### 3.4 [CRITICAL] FR-3a makes the oracle optional; FR-29, §3 and §5 make it mandatory

- `prd.md:52` (§3): "**Admission criterion ... the change must be *fast to verify*** — its acceptance criteria expressible as Playwright assertions. **This makes the oracle the gatekeeper**: work that cannot be verified deterministically does not enter."
- `prd.md:119` (FR-3a): "Every command is optional. **A repository may define none.** Workflow steps bound to an undefined command are **skipped and recorded as skipped — never failed**".
- `prd.md:177` (FR-29): "Run Playwright E2E against a prod-like environment with a real database as the baseline oracle **before any PR is offered for human review**."
- `prd.md:87` (§5 step 11): "one PR per touched repository, **each with green Playwright E2E against a real database**."
- `prd.md:192` (FR-40): open a PR "when an epic's workflow completes **with all gates satisfied**".

For a repository with no `e2e_command`, exactly one of these must break:
- FR-3a is honoured → the E2E step is skipped → FR-29 is violated and §5 step 11's promise is false;
- FR-29 is honoured → the story cannot produce a PR → the step *is* effectively a failure, contradicting FR-3a's "never failed";
- FR-40 opens the PR anyway → "all gates satisfied" is true of a run whose oracle was absent, which is precisely the green-when-unvalidated failure FR-28 exists to prevent.

This is not hypothetical. **Q6 (`prd.md:265`) states the dogfood repository has no Playwright suite yet** — "For `ai-orchestrator`, unit tests (TDD) and E2E ... are built during bootstrapping." So the FR-3a path is the live path for one of the PoC's two repositories on day one, and §11's assumption at `prd.md:276` concedes it.

Related gap: **no FR implements the §3 admission criterion.** There is no requirement that anything checks, at intake or at G1b, that a change's AC are Playwright-expressible before it enters the pipeline. The "gatekeeper" is prose only.

### 3.5 [CRITICAL] Phase A and Phase B run in different working directories; C-4 says a session cannot be resumed across that boundary

- `prd.md:148` (FR-12b): Phase A clones/refreshes every repo at base branch. "**No branches are created at this point.**"
- `prd.md:149` (FR-12c): Phase B, after G2, creates a branch and **git worktree** only in affected repos.
- `prd.md:248` (C-4): "**The session key encodes the working directory, so the resuming host must match it.**"
- `prd.md:166` (FR-22): persist enough state to "reconstruct or resume a session after container replacement".
- `prd.md:159` (FR-19a): a G3 rejection "**resum[es] the existing harness sessions** ... rather than starting cold."
- `prd.md:69` (§4): the human "**resumes** that session as a chat through the SSH command line."

The shaping session in §5 step 3 is created in the **Phase A workspace path**. Every downstream build, escalation and review-loop session lives in the **Phase B worktree path** — a different directory, created later, at a path not known at Phase A time. By C-4's own stated mechanism, sessions are not resumable across that move. Three separate features (FR-19a review loops, FR-23/FR-35 blocked-step resume, §4 interactive chat) are built on a resume that the PRD's own constraint section says will not work as designed, and `addendum.md:46` repeats the cwd requirement. Nothing in §6 requires a stable, pinned project-dir identity independent of the physical path.

### 3.6 [HIGH] FR-30 escalates on essentially every task, which defeats asynchrony and makes §2's ≥60% target unreachable

- `prd.md:168` (FR-24): "**Require every agent task** to return schema-validated structured output containing at minimum: `status`, `artifacts_written`, `open_questions`, `assumptions`."
- `prd.md:178` (FR-30): "**Escalate to a human when an agent returns non-empty `open_questions` OR non-empty `assumptions`**".
- `prd.md:33` (§2): "Epics reaching human review **without intervention** | ≥ 60%".
- `prd.md:14` (§1): the orchestrator "stops for a human **only on two events**".

Every non-trivial coding task makes assumptions; a schema that mandates the field invites the model to populate it. FR-30 as written therefore fires on close to 100% of tasks. There is no severity threshold, no assumption-classification requirement, no "material assumption" definition, and no requirement that the orchestrator triage before escalating. The ≥60% no-intervention target and §1's "only on two events" cannot survive FR-30's literal reading.

Note this is a *correct* implementation of forge hardening #2 colliding with a *correct* implementation of forge Lock #1 (asynchronous gates, epic as return unit). The PRD inherits both and never reconciles them. See §4.5.

### 3.7 [HIGH] The template library is named three different ways across FR-7a, FR-11a and addendum §D2

| Source | Template names |
|---|---|
| `prd.md:127` (FR-7a) | `new-feature` → `epics` → `stories` |
| `prd.md:133–140` (FR-11a) | **`new-feature`**, **`epics`**, **`stories`** |
| `prd.md:142` (FR-11b) | "The **`intake`** template branches on its variant" |
| `addendum.md:103–107` (§D2) | **`intake`**, **`epic`**, **`story`** |

FR-11b references a template `intake` that FR-11a's own table does not define. §D2 — the section the PRD points to for template detail — uses a third, singular naming scheme throughout. FR-11a says "**No per-project bespoke workflows**" and §D2 says "Three authored templates" — the count agrees, the identifiers do not. Any downstream story that says "implement the `intake` template" is ambiguous.

The *content* also differs: FR-11a gives `new-feature` three phases (intake → architect/plan → epic split) and says it references `epics`; §D2 gives `intake` a seven-step span ending at G2 with **no reference to `epic` at all**, and moves branch/worktree creation and PR opening into `epic`. These are two different decompositions.

### 3.8 [HIGH] FR-11b and the §5 gate table disagree on which bugfix gate survives

- `prd.md:94` (§5 table): G1a's Bugfix column reads "**merged into G1b**"; G1b's reads "✓".
- `prd.md:142` (FR-11b): "`bugfix` **skips architecture** and runs **a single intake checkpoint**."
- `prd.md:80` (§5 step 4): "*(A bugfix skips this step; intake produces stories directly.)*"

G1b is defined (`prd.md:94`) as the gate that happens "**After architecture and epic planning**". If bugfix skips architecture and epic planning, the surviving gate is structurally G1a with G1b's payload folded in — the opposite of the table's "G1a merged into G1b". More seriously, this breaks the signature chain: see §4.1.

### 3.9 [HIGH] FR-4 registers static GitHub tokens; SEC-1 and FR-39 forbid them

- `prd.md:120` (FR-4): "**Register per-repository credentials: GitHub token**, and any environment variables agent tasks need."
- `prd.md:228` (SEC-1): "Repository-scoped, **short-lived** tokens. **Never long-lived** org-wide credentials."
- `prd.md:191` (FR-39): "Create branches, commit, and push using repository-scoped **short-lived** credentials."

A token a human registers once and stores is by definition long-lived. Nothing in §6 requires a GitHub App installation, a token-minting/exchange service, or a refresh mechanism — the only capability that would let FR-39 and SEC-1 be satisfied. FR-4 as written is the mechanism SEC-1 prohibits.

### 3.10 [MEDIUM] FR-7 offers `parallel` composition and `run.container`; FR-47/48 and §3/NFR-1 rule both out

`prd.md:126` (FR-7) lists step types including `run.container` and **`parallel`** composition.
- `parallel` vs FR-47/FR-48: the DSL can express what the runtime must reject. Either the schema should omit it for the PoC or FR-48 should state that in-workflow `parallel` is exempt (it plausibly is — parallel steps within one run share one worktree — but the PRD never says).
- `run.container` vs `prd.md:62` ("**Multi-container execution**" out of scope) and NFR-1 ("**Single** Docker container"): running a container step from inside the single container requires docker-in-docker/socket mounting, which SEC-3's hardening (`prd.md:230`, read-only rootfs, dropped capabilities) works directly against. No FR or NFR provisions it.

### 3.11 [MEDIUM] FR-19c describes a state the documented lifecycle cannot reach

`prd.md:161` (FR-19c): "A story **whose PR already merged** cannot simply be re-run."

Per FR-42 (`prd.md:195`) merge is a human action only, and per FR-40a (`prd.md:193`) an epic's PRs are presented "to G3 as **one reviewable unit**". The two G3 outcomes in §5 step 11 are "runs the feature herself, then merges — **or** sends the epic back for a fix cycle." There is no described path where the human merges *some* PRs and then rejects the epic, which is the only way FR-19c's precondition arises. Either the partial-merge path is real and §5/FR-36/FR-40a must describe it, or FR-19c guards an unreachable state.

### 3.12 [MEDIUM] §3 puts a conversational planning UI out of scope; §4 requires building one

- `prd.md:63` (§3 Out of scope): "**A conversational planning UI.** See §4."
- `prd.md:69` (§4): "**A custom web interface** fronting Apache Guacamole, installed in the infrastructure, connecting over SSH."
- `prd.md:87`/`prd.md:80` (§5 step 3): the shaping session runs "in a harness she reaches through the **web chat** (§4)."

The out-of-scope entry points at §4 as its justification, and §4 specifies a custom web interface for conversing with a planning session. The distinction intended is presumably "we don't build the *chat semantics*, only a terminal gateway" — but §3 as written disclaims a thing §4 and §5 both require. See also §5.2: no FR covers it at all.

### 3.13 [MEDIUM] FR-12e requires a green baseline using a command FR-3a makes optional

`prd.md:151` (FR-12e): "**Run the target repository's test suite** after worktree creation to establish a known-clean starting point, and **fail the story early if it is already red**." With `unit_test_command` undefined (FR-3a), there is no baseline and no red/green signal, yet FR-3a forbids treating the skip as a failure. The "known-clean starting point" is then asserted, not established.

### 3.14 [MEDIUM] FR-28a is a liveness check presented as validation — the framing §E explicitly rejects

- `prd.md:175` (FR-28a): "**Checkpoint validation:** ... confirm the expected artifacts ... **exist and are well-formed**".
- `prd.md:81` (§5 step 5): "She triggers **checkpoint validation**. The orchestrator inspects the session output ... and confirms **the artifacts exist and are well-formed**."
- `prd.md:174` (FR-28): "File-existence checking is **liveness** and must never be presented as correctness."
- `addendum.md:121` (§E, from the forge): "File-existence as validation | A **liveness** check."

FR-28a is file-existence plus a parse. It is named "validation", it sits on the critical path into G2, and — unlike every other step — **it never declares its FR-27 gate strength**. Nothing requires the UI to render it as `liveness`. This is the rejected framing surviving under a different name.

### 3.15 [MEDIUM] `addendum.md:137` (verification item 7) mandates the manual baseline `prd.md:286` (§12.1) rejects

- `addendum.md:137`: "**Establish a manual baseline on two or three comparable features — before the pipeline exists**, or the 'better than by hand' question can never be answered honestly (§12)."
- `prd.md:286` (§12.1): "**A rigorous manual baseline — build the same feature twice — is not worth doing.** ... it delays the build for a contaminated number. **Three cheap instruments instead.**"

Both cite §12 as their authority and reach opposite conclusions, and the addendum's item is in a list titled "Before architecture commits to any of this." One of them has to go.

### 3.16 [LOW] FR-4a vs SEC-5 is *not* a contradiction — flagged as checked

`prd.md:121` (FR-4a) pre-empts this explicitly: "*(Distinct from SEC-5: secrets remain scoped per project because that boundary constrains the **agent**, not the human.)*" That reasoning holds; single-operator authn and per-agent secret partitioning are orthogonal, and §11 (`prd.md:273`) restates it consistently. **However, see §3.17 for the version of this conflict that is real.**

### 3.17 [HIGH] SEC-5's enforcement is defeated by NFR-1 and SEC-9, both of which the PRD accepts

- `prd.md:232` (SEC-5): "Scope secrets per project; a task for project A can **never** read project B's credentials — **enforced** even though the PoC has one operator."
- `prd.md:215` (NFR-1): "**Single Docker container** for the PoC."
- `prd.md:236` (SEC-9): the Guacamole SSH path "is an **interactive shell into the execution container** ... It **bypasses every workflow gate by construction**."

One container running both projects' work, plus an interactive shell into it, gives any process (and the human, and any agent that achieves command execution under the §8 threat model of "prompt injection reaching an agent") access to whatever secret material is resident. SEC-5 says "enforced"; the PoC architecture provides no enforcement boundary. SEC-6's credential-injection-at-the-proxy is the mechanism that would fix it — and SEC-6 says "**Prefer**", not "require". For a control the PRD justifies on the grounds that "retrofitting this boundary later is far harder", "prefer" is the wrong strength.

---

## 4. Upstream fidelity — `forged-idea.md`

This is where the document diverges most from its source, and mostly without saying so.

### 4.1 [CRITICAL] Hardening #1 reversed: the human signs the prose, not the executable spec

**Upstream (`forged-idea.md:25`):** "**Human signs the executable spec, not the prose.** If an agent translates AC → Playwright and nobody reads the spec file, drift re-enters through the translation. Name which artifact carries the signature."

**PRD:** Q1 (`prd.md:260`) answers "the **Given/When/Then acceptance criteria in `epics.md`**" — a prose artifact. `prd.md:100` then asserts "**G1b carries the signature that anchors the oracle.** A Playwright spec derived from criteria signed before implementation cannot be a mirror of that implementation."

That assertion answers a *different* objection. The forge's concern was never mirroring — it was **translation drift between signed prose and generated spec**, which precedence in time does nothing to prevent. FR-28b (`prd.md:176`) requires bidirectional coverage reporting ("any acceptance criterion with no corresponding spec, and any spec with no corresponding criterion") and traceability — good, and necessary — but **coverage is not correctness**. A Playwright spec can cover every criterion and assert the wrong thing on each. No FR requires a human to read, approve, or sign the generated Playwright spec; there is no gate between FR-28b's translation and the build steps.

The hardening item was answered in name (an artifact is named) and reversed in substance (it is the prose one). `addendum.md:136` demotes the residual risk to a pre-architecture verification item rather than a requirement.

**Fix:** add a G1c — or extend G2 — to cover human sign-off on the generated `.spec.ts` files, and give FR-28b a `human` gate strength under FR-27.

### 4.2 [CRITICAL] Locked decision reversed: "fixes go to a new chat session"

**Upstream (`forged-idea.md:16`, under "## Locked"):** "**Fixes go to a new chat session against the epic.**"

**PRD (`prd.md:159`, FR-19a):** "A G3 rejection re-runs the epic and its stories, **resuming the existing harness sessions** with the context of what changed, **rather than starting cold. Agents retain their prior reasoning.**"

**Q10 (`prd.md:269`)** confirms and hard-codes it: "**resuming the existing sessions** ... so agents keep their prior reasoning."

This is a direct 180° reversal of a **Locked** item, presented as a resolution rather than a change, with no acknowledgement that upstream decided the opposite. The forge's rationale for a fresh session is unstated in `forged-idea.md`, but the obvious one — an agent that produced rejected work carries the reasoning that produced it, and resuming re-anchors on exactly that — is the *inverse* of FR-19a's stated benefit ("agents retain their prior reasoning"). One of the two positions is wrong; the PRD does not argue the case, it just adopts the other one.

It also creates a coupling the PRD is not aware of: FR-19a is now a hard dependency on the resume path that §3.5 above shows is architecturally fragile, whereas the upstream "new session" design had no such dependency.

**Fix:** either restore fresh-session-per-fix, or add an explicit "Reversal from forge" note with the argument, the way §5's `prd.md:102` blockquote handles the BMad deviation.

### 4.3 [CRITICAL] Locked decision hollowed out: "parallelism across projects is what amortizes the human ceiling"

**Upstream (`forged-idea.md:12`, Locked):** "Human gates are asynchronous; **parallelism across projects is what amortizes the human ceiling.**"
**Upstream (`forged-idea.md:9`):** "across **parallel pipelines**."

**PRD:** Q7 (`prd.md:266`) "**no concurrency in the PoC**"; FR-47 "the PoC iterates through epics **sequentially**"; FR-48 no two runs may share "a worktree **or a database**" against NFR-1's single Postgres.

The forge offered two ways to satisfy hardening #4 (`forged-idea.md:28`): "**Isolate the E2E environment per run** (ephemeral DB or schema-per-run, dynamic ports), **or** serialize runs per repo." The PRD takes the second — which is permitted — but then widens it past "per repo" to global epic sequencing, and never notices that doing so removes the mechanism the Locked item identifies as the source of the product's economics. §1 keeps the parallelism claim (§3.1 above); §6's blockquote defends the serialization on its own merits without ever weighing it against the lock.

**Fix:** adopt schema-per-run + dynamic ports (cheap, and exactly what the forge named first) so per-project parallelism survives, or explicitly record that the PoC deliberately does not test the parallelism premise — which materially weakens what a successful PoC would prove.

### 4.4 [CRITICAL] Upstream success metric demoted, and its kill threshold dropped entirely

**Upstream (`forged-idea.md:33–36`):** "**Success metric for the PoC: Human-minutes per merged PR, versus the same person writing it by hand.** Instrumented in Langfuse **from day one**, same trace id. **'It produced a PR' is not the metric.** **If the ratio is ~1.1x on the easy ticket class, the idea does not survive contact with the hard class.**"

**PRD §2 (`prd.md:22–27`):** Primary metrics are **token cost per issue/repo/project** and **velocity spec→PR merged**. The upstream primary metric appears nowhere in §2's tables; it survives only as FR-50/51/52 in §12.1's "three cheap instruments", and Q4 (`prd.md:263`) marks the question "**Partially resolved** — the human-attention question is **unresolved**."

Two losses:
1. **Priority inversion.** The one metric the forge said decides whether the project was worth building is not a primary metric. §12.1 (`prd.md:284`) states the problem plainly — "Neither answers 'is this better than doing it myself?' — the question that decides whether the project was worth building" — and then does not promote the metric that does.
2. **The kill threshold is gone.** `forged-idea.md:36` names a specific number at which the idea dies (~1.1x). FR-51 (`prd.md:203`) computes `estimated_manual_minutes ÷ actual_human_minutes` but **no target, threshold or decision rule for it appears anywhere** — not in §2's tables, not in §12. A ratio with no threshold is a dashboard, not a test. Note also that FR-51's ratio is inverted relative to the forge's "human-minutes vs. by hand" phrasing (>1 is good in FR-51, ~1.1x is *bad* upstream) — the two are not directly comparable, and neither is defined against the other.

**Fix:** promote FR-50/51 to §2's primary table and carry the ~1.1x kill criterion forward as an explicit PoC decision rule, in FR-51's own units.

### 4.5 [HIGH] Locked "unit of human return is the epic" is contradicted by FR-30 and never reconciled

**Upstream (`forged-idea.md:13`, Locked):** "**Unit of human return is the epic**, not the story or the PR."

FR-30 (`prd.md:178`) escalates on any non-empty `open_questions` **or** `assumptions` from any agent task — a *sub-story* trigger (§3.6). §1 (`prd.md:14`) tries to hold both ("stops for a human only on two events: an epic completing, **or a story blocking**"), and §2 concedes 40% of epics will be interrupted. Hardening #2 (`forged-idea.md:26`) demanded FR-30, so this is inherited tension, not invention — but the PRD adopts both sides without deciding how they compose, without a materiality filter, and without adjusting the Locked claim.

### 4.6 [HIGH] Rejected scope re-expanded: the forge specified **one repo**, the PRD's PoC has two and adds cross-repo machinery

**Upstream (`forged-idea.md:19`, under "## Rejected, and why"):** "Generic 'issue → PR' as first scenario ... **PoC targets one repo, one ticket class**: slow-to-write, fast-to-specify, fast-to-verify."

**PRD §5 (`prd.md:75`):** "Rebeca, sole operator, **two repositories**". And the PRD builds a cross-repository apparatus on top: FR-12d (one story ↔ one repo, multi-repo features become multiple stories), FR-40 (one PR per touched repo), FR-40a (multiple PRs as one G3 unit, no atomic merge), Q8, plus Phase A/Phase B (FR-12b/12c) which exists *only* because multiple repos must be prepared before knowing which are touched.

The ticket-class half of the rejection is honoured well (Q5, §3 admission criterion). The one-repo half is silently dropped, and it is the half that keeps the PoC cheap. Meanwhile §12.2 (`prd.md:296`) argues "**build nothing**" for cross-repo *ownership* while §6 builds substantial cross-repo *mechanism* — the two sections point opposite directions on the same axis.

### 4.7 [HIGH] Hardening #6 scope-creep: the front-end was scoped to the review inbox alone

**Upstream (`forged-idea.md:30`):** "**Front-end PoC scope is the review inbox, not the workflow designer**: what needs my gate, on which project, with enough context to reload cold. This is the feature the async model actually depends on."

**PRD** honours the inbox (F6, FR-33–37, and FR-34 quotes the "reload cold" language directly). But it adds two more front-end surfaces:
- **FR-12 / FR-12a** (`prd.md:144–145`): workflow viewing UI + a plan-approval UI (G2). Read-only, so not a "designer" — but it is a second screen with its own rendering of workflow graphs.
- **§4 / §5 step 3** (`prd.md:69`, `prd.md:80`): "a **custom web interface** fronting Apache Guacamole" — a terminal/chat surface, plus Guacamole itself as new infrastructure that `addendum.md:54` admits "**the PoC's single-container assumption does not cover** — it sits alongside, not inside."

Three surfaces where the forge scoped one, and the third drags in an out-of-container dependency that NFR-1 does not account for.

### 4.8 [HIGH] Hardening #7 softened: "do not rely on harness session-id resume" became "rely on it, via a vendor store"

**Upstream (`forged-idea.md:31`):** "**Do not rely on harness session-id resume.** That state is container-local ... container death or the stated v2 multi-container plan destroys it. **Persist the transcript and the inputs needed to *reconstruct* a session.**"

**PRD:** FR-21 makes session-id persistence "a **hard requirement**" and states that without it "no blocked step can be resumed and no review loop can retain agent reasoning (FR-19a)" — i.e. the design is now *predicated* on resume. FR-22 says "reconstruct **or** resume", and C-4 (`prd.md:248`) closes with "This resolves the container-local state risk carried over from the forge."

But the upstream ask was for the **reconstruct** path — persist the transcript and the inputs — as insurance against the resume path failing. **No FR requires persisting a transcript.** FR-22's "or" makes reconstruct optional; NFR-6 (`prd.md:220`) retains "agent task logs and structured outputs", which is not the same as a replayable transcript. The mitigation adopted (SDK `sessionStore` over Postgres) is a *different* dependency, not the requested fallback — and C-4's own next sentence ("the resuming host must match [the working directory]") plus `addendum.md:46` show the new dependency has its own container/path coupling (§3.5). Claiming the risk is "resolved" overstates it.

**Fix:** make FR-22 conjunctive — persist transcript **and** reconstruction inputs — and drop or qualify C-4's "resolves".

### 4.9 [MEDIUM] Hardening #3 honoured in definition, orphaned in obligation

`forged-idea.md:27`: "**Label gate strength in the orchestrator.** Every step declares liveness / deterministic-oracle / adversarial / human. Any stage with no oracle is **explicitly marked unvalidated** rather than shown green."

FR-27 and FR-28 state this exactly. But (a) FR-27 is referenced by nothing (§1.3); (b) no FR requires gate strength to be part of the FR-6 workflow schema, so there is nothing to declare it *in*; (c) FR-41 reports "gate status" to the PR, not gate strength; (d) FR-28a, the one step whose strength is most easily mistaken, never declares one (§3.14); (e) the `adversarial` strength is defined and **no workflow step anywhere in the PRD or `addendum.md` §D2 uses it** — the `story` template (`addendum.md:107`) has no refutation step.

### 4.10 [LOW] Rejected items correctly honoured — verified

For completeness, these upstream rejections **are** honoured cleanly: CNCF Serverless Workflow DSL as a dependency (`prd.md:58`, `addendum.md:21–24`, vocabulary retained as instructed); Kestra visual editor (`prd.md:59`, `addendum.md:26`); file-existence-as-validation *as a stated principle* (FR-28 — though see §3.14 for the practice); agent-generated E2E as oracle (`prd.md:102` deviation note, `addendum.md:124`). The two surviving weak points (`forged-idea.md:38–46`) are carried faithfully into §12.1 and §12.2, and §12.1's instrument design is a genuine improvement on the upstream text.

---

## 5. Unstated dependencies

### 5.1 [CRITICAL] Nothing provisions the prod-like E2E environment that FR-29 mandates and FR-49 tears down

§6 F9 is titled "**Test environment provisioning**" and contains FR-47 (serialize), FR-48 (enforce serialization), FR-49 (**tear down** the environment). **There is no requirement that creates one.** FR-29 requires "a prod-like environment with a real database"; forge hardening #4 named the components ("ephemeral DB or schema-per-run, **dynamic ports**"); NFR-1 provisions "a Postgres it can reach" for the *orchestrator*, not per-run test databases; §11 (`prd.md:275`) assumes repos "can run their test suites inside the single container without external service dependencies beyond a database" — a database, singular, which FR-48 then forbids two runs from sharing.

The oracle the entire product rests on has no requirement that stands it up. A teardown requirement for an environment nothing creates is the clearest possible signal that a requirement was lost in editing.

### 5.2 [HIGH] §4's Guacamole/SSH mechanism has zero functional requirements

§4 is a full section resolving Q3, §5 step 3 depends on it for the shaping session, and `addendum.md:49–54` details it. Yet **no FR mentions Guacamole, SSH, the web chat, or interactive session access**. The only normative statements are NFR-8 (`prd.md:222`, must be traced) and SEC-9 (`prd.md:236`, must be authenticated, scoped, audited) — both of which *constrain* a capability nothing *requires*. The primary journey's step 3 therefore has no requirement backing it, and §3 lists a conversational planning UI as out of scope (§3.12). `addendum.md:54` additionally flags it as infrastructure "the PoC's single-container assumption does not cover", which NFR-1 does not accommodate.

### 5.3 [HIGH] FR-43/44/45/26/SEC-8 depend on a gateway and a telemetry backend that no requirement deploys

FR-26 (per-task token usage and cost), FR-43 (one trace per run, shared trace id), FR-44 (cost attribution across five dimensions), FR-45 (per-run and per-project budget enforcement with halt), SEC-8 (per-project virtual keys and budgets), and C-6/C-7 all presuppose **LiteLLM and Langfuse**. Those names appear only in `addendum.md` §C. No FR or NFR requires deploying a model gateway or a trace backend; NFR-1's container inventory (`prd.md:215`) lists "orchestrator, tooling (git, gh, Claude Code, Codex, skills), and a Postgres" — neither is in it. C-6 (`prd.md:252`) even states FR-43 *depends* on gateway-specific configuration, which is a dependency on a component the requirements never call for.

### 5.4 [HIGH] FR-21's "assign the identifier before launch" is not achievable on Codex, which FR-20 requires

- `prd.md:165` (FR-21): "**Assign the identifier before launch rather than parsing it from output. This is a hard requirement.**"
- `prd.md:164` (FR-20): execute against "a configured harness (**Claude Code, Codex**)".
- `addendum.md:42`: Claude Code — "pre-assign with `--session-id <uuid>`. No output parsing." ✅
- `addendum.md:57`: Codex — "**Session id from the `thread.started` event**" — i.e. parsed from output. ❌

FR-21 is stated as unconditional and "hard", and one of the two named harnesses cannot satisfy it. C-5 (`prd.md:250`) catalogues Codex's gaps (defer round-trip, tracing) but **not this one**, and its "declared capability" model (`addendum.md:61`) lists `supports_defer`, `supports_native_tracing`, `supports_structured_output`, `supports_resume` — no `supports_preassigned_session_id`. §4's ordering argument ("there is no path where a human starts a session the orchestrator does not know about", `addendum.md:52`) also rests on pre-assignment and therefore does not hold for Codex.

### 5.5 [HIGH] FR-33's inbox has two item types; at least six things escalate to it

`prd.md:183` (FR-33): the inbox lists items "with type (**blocked story / epic ready for QA**), age, and project."

Escalation sources not representable in either type:
| Source | Escalates | Inbox type? |
|---|---|---|
| FR-16 (`prd.md:155`) | task failure (vs. infra failure) | — |
| FR-19 (`prd.md:158`) | rework cap exhausted | — |
| FR-30 (`prd.md:178`) | non-empty `open_questions`/`assumptions` | arguably "blocked story", but the agent is *not* blocked — that is the whole point of FR-30 |
| FR-45 (`prd.md:200`) | budget breach, "halt and escalate" | — |
| FR-52 (`prd.md:204`) | sustained zero rejection rate alert | — |
| FR-5 (`prd.md:122`) | repository validation failure | — |
| G1a / G1b / G2 | three gates that need a human decision | — |

Notably the **gates themselves** have no inbox type, despite FR-51 (`prd.md:203`) requiring "active time inside every gate ... derived from timestamps the orchestrator already records" and §2's counter-metric (`prd.md:41`) saying gate time is "**derived automatically from inbox timestamps**". If gates are not inbox items, that derivation has no source.

### 5.6 [MEDIUM] FR-28b's two-way coverage check requires an AC identity scheme nothing specifies

FR-28b (`prd.md:176`) requires reporting "any acceptance criterion with **no corresponding spec**, and any spec with **no corresponding criterion**", with the translation "traceable back to the signed criteria". This needs stable, machine-readable identifiers on each Given/When/Then block in `epics.md` and a persisted mapping. No FR requires `epics.md` to have a parseable structure, criterion ids, or a stored AC↔spec map. Q1 (`prd.md:260`) defers the format to "per `bmad-create-epics-and-stories`", an external skill whose output format the PRD does not pin.

### 5.7 [MEDIUM] FR-32 records "which artifact version" was approved; nothing versions the artifact

`prd.md:180` (FR-32): record each gate decision "**against which artifact version**". FR-9 versions *workflow documents*. Nothing versions `epics.md` — the artifact that actually carries the G1b signature (Q1). Worse, `epics.md` is produced in the **Phase A workspace** (FR-12b), which by FR-12b's own text has **no branch**, and SEC-7 (`prd.md:234`) forbids agents pushing to a default branch. So the signed artifact has no branch to live on, no version identity, and no requirement placing it in the Phase B worktree that the build steps use. The signature chain that §4.1 already weakens has no storage requirement underneath it.

### 5.8 [MEDIUM] FR-19a needs the rejection reason; FR-36 does not capture one

FR-19a (`prd.md:159`) resumes sessions "with **the context of what changed**". FR-36 (`prd.md:186`) provides only "**Approve or reject** an epic at final QA". No requirement captures rejection rationale, the failing observation, or which stories are implicated. FR-32 records "what was approved", not why something was rejected. FR-52 (`prd.md:204`) tracks rejection *rate* but not rejection *content*.

### 5.9 [MEDIUM] `addendum.md:16` requires object storage; no FR or NFR provisions it

"Python serializes with pickle; 1GB field cap → **store artifacts in object storage, pass pointers**." NFR-1's container inventory has no object store, and no FR requires artifact storage. FR-24's `artifacts_written`, FR-34's diff/trace links, and NFR-6's retained logs all imply one.

### 5.10 [MEDIUM] FR-7a sub-workflows vs. the DBOS limitation in `addendum.md:18`

`addendum.md:15`: "**Cannot start or enqueue workflows from inside a step.**" FR-7 models `run.workflow` as a *step type* alongside `run.shell` and `run.agent`. If the DSL interpreter is "one `@DBOS.workflow()`" (`addendum.md:11`) whose step types are all `@DBOS.step()`, then `run.workflow` cannot be a step. Resolvable (child-workflow invocation from the workflow body), but the PRD's uniform "step type" framing hides the exception, and FR-7b's version-pinned resolution of referenced workflows adds a second constraint on the same mechanism.

### 5.11 [LOW] NFR-3 justifies itself with a mode NFR-4 tells you not to use

NFR-3 (`prd.md:217`): "Agent containers run as a non-root user. **Permission-bypass modes** refuse to start as root". NFR-4 (`prd.md:218`): "**Prefer an explicit tool allowlist over blanket permission bypass**". The stated reason for NFR-3 is a property of the mode NFR-4 rejects. Non-root is right regardless; the rationale is borrowed from `addendum.md:91` without adjusting for NFR-4's choice.

### 5.12 [LOW] FR-18 rolls back "its working branch"; Phase A has no branch

FR-18 (`prd.md:157`): "Cancel a run and **roll back its working branch**." A run cancelled during Phase A (FR-12b) or before G2 has no branch and no worktree — only a refreshed clone. Nothing specifies cancellation cleanup for the Phase A workspace, or removal of the worktrees FR-12c created. FR-49 covers only the test environment.

---

## 6. Prioritised remediation

| # | Finding | Severity | Location |
|---|---|---|---|
| 1 | "Fixes go to a new chat session" (Locked) reversed by FR-19a/Q10, unacknowledged | critical | §4.2 |
| 2 | Signature sits on prose AC, not the executable spec — hardening #1 answered in name only | critical | §4.1 |
| 3 | FR-47/48 + NFR-1 eliminate all run concurrency; §1's parallel pipelines and Locked #1 are void | critical | §3.1, §4.3 |
| 4 | FR-3a (oracle optional) vs FR-29/§3/§5 (oracle mandatory); Q6 confirms it bites on day one | critical | §3.4 |
| 5 | Phase A/Phase B working-directory split breaks the resume C-4 requires and FR-19a/§4 depend on | critical | §3.5 |
| 6 | Upstream primary metric demoted to a §12 instrument; ~1.1x kill threshold dropped entirely | critical | §4.4 |
| 7 | Rework cap escalates to the human it is escaping; no terminal state defined | critical | §3.2 |
| 8 | Nothing provisions the E2E environment FR-29 mandates and FR-49 tears down | critical | §5.1 |
| 9 | FR-21 "pre-assign, never parse" declared hard, unachievable on Codex (FR-20) | high | §5.4 |
| 10 | Template library named three ways (`new-feature`/`epics`/`stories` vs `intake`/`epic`/`story`) | high | §3.7 |
| 11 | FR-30 escalates on nearly every task; §2's ≥60% and §1's "only two events" unreachable | high | §3.6, §4.5 |
| 12 | Forge's one-repo PoC scope silently expanded to two repos + cross-repo machinery | high | §4.6 |
| 13 | Hardening #7 softened: reconstruct-path made optional, risk declared "resolved" | high | §4.8 |
| 14 | §4's Guacamole mechanism has no FR; §3 lists it out of scope | high | §5.2, §3.12 |
| 15 | FR-4 static tokens vs SEC-1/FR-39 short-lived; no minting mechanism required | high | §3.9 |
| 16 | SEC-5 "enforced" defeated by NFR-1 single container + SEC-9 shell; SEC-6 only "preferred" | high | §3.17 |
| 17 | Gateway + telemetry backend required by 6 requirements, deployed by none | high | §5.3 |
| 18 | FR-33's two inbox types vs six-plus escalation sources; gates absent despite FR-51/§2 | high | §5.5 |
| 19 | Front-end scope crept from one surface (inbox) to three | high | §4.7 |
| 20 | `addendum.md` §B self-contradicts on cwd-matching for resume | high | §2.8 |

Medium and low findings are inline above (§1.2, §1.3, §2.1–2.7, §3.3, §3.8, §3.10–3.15, §4.9, §5.6–5.12).

---

## 7. What the document does well

Recording these so remediation does not damage them: FR-28b's bidirectional AC↔spec coverage check is stronger than the upstream ask; §12.1's three-instrument design (FR-50/51/52) is a genuine improvement on `forged-idea.md`'s untested-bet paragraph, and FR-52's "a gate with a 0% rejection rate is not a gate" is the sharpest requirement in the document; §6's serialization blockquote (`prd.md:211`) argues its trade honestly rather than hiding it; the §5 BMad-deviation blockquote (`prd.md:102`) is exactly the form every other upstream departure in §4 should have taken and did not; and §12.4's residual-risk statement — "a good result does not generalize" — is the kind of admission most PRDs omit.
