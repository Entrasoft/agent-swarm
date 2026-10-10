# Coordination v0.3 proposal: shared stepping stones on an open record

**Status: Stages 0 and 1 approved by the owner on 2026-10-10 (offline only: no
model requests and no API spending). Stages 2–4 remain proposed and need
separate approval.** It responds to the standard in
[publication notes](publication-notes.md): a later proposal should justify its
task and scale before observing outcomes, distinguish observable reuse from
unassigned organization and from improved verified results per resource budget,
and state what would warrant stopping. The pause on experiments remains in
effect until the owner approves a specific stage below.

Prepared 2026-10-10. Revised the same day after a literature and record review,
summarized in [Context](#context-as-of-2026-10-10) with sources at the end.

## Question and intended contributions

Can a small team that shares verified intermediate results reach a better
verified outcome than the same number of isolated agents, **at the same total
token budget**, on a problem whose best-known value is not proven optimal?

The study is designed so that either of two contributions is publishable on
its own:

1. **A methods result.** A controlled answer, positive or null, to whether
   sharing beats best-of-N at matched tokens, and whether the answer depends on
   the agents having different strategies. Best-of-N means N independent
   agents, keeping the best answer.
2. **A mathematical result, if one occurs.** An improvement to a public
   best-known record, with a certificate anyone can check. This is a possible
   bonus, not the basis of the design.

## Context as of 2026-10-10

### Proofs of open problems are no longer a frontier for a study this size

On 2026-10-06 OpenAI posted about 720 AI-generated manuscripts to
[github.com/openai/math](https://github.com/openai/math), grouped into 372
problem families. Reported claims include cases of well-known conjectures and
23 Erdős problems.

- **Method.** OpenAI's account is that an unreleased internal model produced
  nearly every result from a single prompt to a single agent, averaging about
  three hours of compute per result. Prompts and per-result compute were not
  released.
- **Verification.** None of the papers is peer reviewed. The README reports
  roughly 42% of top-line results formalized in Lean. Three manuscripts were
  withdrawn the next day over a sign error. Commentators found at least one
  Lean file proving a weaker statement than its paper claims.
- **Reaction.** The erdosproblems.com maintainer froze new proof claims. An
  association of mathematicians chaired by Terence Tao called for a boycott,
  and others criticized the lack of transparency and the volume of unreviewed
  work. Some mathematicians supported public release.

Two conclusions matter for this proposal. First, single agents with large
budgets now reach many mid-tier open problems, so a modest team should not try
to compete on proofs. Second, the community's objections concern transparency,
verification and credit. A study that releases its prompts, budgets, every run
and every failure answers those objections directly, and this repository
already works that way.

### Record improvements are within reach of modest budgets, in niches

Recent verifiable records were set cheaply:

- An LLM evolutionary search improved several binary entries in the
  best-known linear codes tables on one GPU in a few hours per experiment
  (LinCodeEvolve, preprint, 2026-09-29). The table maintainer has accepted the
  improvements but has not yet posted them.
- A Claude-based agent set a circle-packing record for n=27 for about USD 15
  of API use (Cognizant, 2026-08).

Heavily worked problems, such as circle packing, kissing numbers and the
EinsteinArena analytic problems, now move by around one part in a million and
draw many competing teams. Less-studied entries in large tables remain
lightly contested.

### The coordination question is open, but has close prior work

- **Matched compute often erases multi-agent gains.** This has been reported
  for reasoning benchmarks (Wang et al., EMNLP 2024; a 2026 study at equal
  thinking-token budgets) and for agentic benchmarks (Kim et al., "Towards a
  Science of Scaling Agent Systems", 2025).
- **The closest prior work is CORAL (2026).** Four co-evolving agents with
  shared memory beat the best of four independent runs on three tasks and
  recorded cross-agent reuse. It did not match token budgets or evaluations,
  had no diversity factor, and reported no statistics.
- **Sharing ablations in evolutionary LLM search are thin.** CodeEvolve
  (2025) found moderate migration between populations helped while full
  migration barely beat none, on one instance with three seeds. "Learning to
  Share" (2026) reports that naive sharing fails to deliver gains.
- **Station (2026)** reported new results on 5 of 12 AlphaEvolve problems with
  agents that share a literature, without an isolated-agent ablation in its
  abstract.

The gap this study fills: an exactly token-matched comparison against
best-of-N, crossing sharing with strategy diversity, with reuse recorded by the
runtime rather than inferred by a model, and enough repetitions for a declared
statistical test.

## Why the earlier studies could not answer this

1. **Messages duplicated what agents already had.** Only whole candidate sets
   travelled, so a peer's set helped only when it was strictly better.
2. **No reusable partial work.** A subset avoiding arithmetic progressions is
   judged whole; one agent cannot extend another's partial answer.
3. **A saturated, solved task.** At m=24 the optimum is ten. Offline agents
   ended with gap one in every condition ([Amendment A](experiment-protocol.md));
   live runs reached eight or nine in every condition
   ([live comparison](live-comparison-results.md)).
4. **Budgets matched by calls**, with coordinator calls taken from the team.
5. **Identical agents**, so pooling added little variety.
6. **Too few rows** to separate a modest effect from noise.

## Task

### Selection criteria

- **An open record:** a best-known value not proven optimal, in a maintained
  public table that accepts improvements.
- **Reusable partial results:** a good answer one agent can modify or extend.
- **Exact, cheap verification** by deterministic code.
- **Compact actions:** progress expressible in a few hundred tokens.
- **Light competition:** entries recent AI systems have not worked over.

### Candidates reviewed

| Candidate | Open record | Reusable partial results | Verification | Competition | Verdict |
| --- | --- | --- | --- | --- | --- |
| **Linear codes over GF(3) or GF(4)** (codetables.de) | Many entries with a gap between lower and upper bounds; maintainer accepting improvements | Yes: a parent code yields derived codes, and a construction can be modified | Exact minimum-distance computation, cheap at small dimension | Recent AI work targeted binary codes at lengths 171–201 | **Primary** |
| Covering designs | Many weak entries; La Jolla repository frozen in March 2026, successor site's submission policy unconfirmed | Partly | Trivial | Light | Alternate |
| Cap sets, dimension 9 and up | Open | Yes, by product constructions | Exact | Light, but the baseline value is unconfirmed | Later study; needs program search |
| Small Ramsey lower bounds | Open | Partly | Exact | Rising; AlphaEvolve improved five in 2026 | Not recommended |
| Circle packing, kissing numbers | Open | Yes | Floating-point tolerance | Very heavy | Not recommended |
| Erdős discrepancy, C=3 | General length open | Yes | Exact | Progress came from SAT solvers | Not recommended for model agents |
| Erdős discrepancy, C=2 | **Solved** (maximum 1,160, Konev and Lisitsa 2014) | Yes | Exact | None | **Fallback**, methods result only |

### Primary task: quasi-cyclic linear codes

For a fixed field q ∈ {3, 4}, length n and dimension k, find a linear code with
the largest minimum distance d. The record table gives the best-known lower
bound on d and an upper bound. An entry is open when they differ.

Agents propose **quasi-cyclic codes**, a standard family in which many table
records were found. A quasi-cyclic code is described by a few polynomials over
GF(q), so an action is a short list of coefficient vectors rather than a full
generator matrix. Good codes are stepping stones: an agent can change one
polynomial of an archived code, or combine polynomials from two archived codes.

The verifier computes the exact minimum distance by enumerating codewords. At
dimension k ≤ 12 over GF(3) that is about 531,000 codewords, which takes
seconds. Stage 0 profiles the practical limit.

**Targets are chosen by a frozen rule before any comparative run.** Take a
dated snapshot of the tables for q = 3 and q = 4. Keep entries where:

- lower and upper bounds differ;
- k is within the profiled verification limit;
- n is admissible for the quasi-cyclic parameterization;
- no AI-produced record appears in the snapshot's history for that entry.

From those, select six target entries by a seeded random draw recorded in the
manifest. Each run works on one target, assigned by the schedule.

**Fallback.** If the snapshot has fewer than six qualifying entries, switch to
discrepancy-2 sequences with the same design. That gives a methods result only,
and the report will say so.

## Design

### Shared archive instead of messages

Replace point-to-point messages and the coordinator role with an **archive**:
the top k = 8 distinct verified codes for the run's target, ranked by
(d, fewer minimum-weight codewords), each with its contributing agent and
event ID.

- In **shared** arms, every agent sees the team archive.
- In **independent** arms, each agent sees an archive of only its own codes,
  with the same size, format and byte limit.

The observation shape is identical across arms. Only the archive's contents
differ, which isolates sharing from context size and prompt format.

An action names an archive entry as its base (or none) and states the change:

```text
{"base": <archive event id or null>, "polynomials": [[...], [...]], "used_event_ids": [...]}
```

The runtime records the base as a provenance parent and measures how far the
new code differs from it. Building on a peer's result is then a fact recorded
by the runtime, not a claim made by the model.

### Diversity

Four strategy instructions, equal in length and detail:

1. Local search: change one coefficient block of the base.
2. Recombination: take polynomials from two archived codes.
3. Algebraic structure: choose polynomials from cyclotomic factors of xⁿ − 1.
4. Weight repair: target the base's minimum-weight codewords.

In **diverse** arms the four agents get four different strategies. In
**homogeneous** arms all four get the same strategy, rotated across blocks so
each is used equally often.

### Arms

| Arm | Agents | Strategies | Archive | Role |
| --- | ---: | --- | --- | --- |
| I-H | 4 | Same | Own results only | **Best-of-N baseline** |
| I-D | 4 | Different | Own results only | Diversity without sharing |
| S-H | 4 | Same | Team-wide | Sharing without diversity |
| S-D | 4 | Different | Team-wide | **Sharing with diversity** |
| Solo | 1 | Rotated by block | Own results only | Depth instead of breadth, same total tokens |

No coordinator and no roles beyond the assigned strategy. Scheduling is
round-based and outcome-blind in every arm; see
[Rounds and batch requests](#rounds-and-batch-requests).

The 2×2 separates two claims:

- **Help:** S-D beats I-H, the best-of-N baseline.
- **Mechanism:** (S-D − I-D) − (S-H − I-H). Strategy instructions could
  improve results on their own; that effect cancels in this contrast, so a
  positive value reflects sharing between different strategies.

Reviewers will likely ask whether naive sharing performs differently from a
curated archive. A full-history arm is a possible addition but would add ten
runs; it is listed under [Deferred](#deferred).

### Budget matching

Every run receives the **same total token and currency allowance**. Decisions
proceed in rounds until the next conservative reservation does not fit, so
`budget_exhausted` is the normal end of a run. Summaries record actual tokens,
cost and decisions per agent. Validator feedback (d and the number of
minimum-weight codewords) is identical in every arm.

### Rounds and batch requests

Each round gives every agent in a run one decision, and **every agent in the
round sees the same archive snapshot**, taken when the round starts. Results
are validated and added to the archive after the round ends. This replaces the
earlier sequential scheduling, in which a later agent could see an earlier
agent's result from the same round. Offline stages use the same round
semantics, so offline and live results are comparable.

Live requests are sent through the provider's **batch interface**, one batch
per round across all runs in the stage. In Stage 4 that is up to 200 requests
per batch: 50 runs × 4 agents, or 1 for solo runs. The reasons:

- **No ambiguous transport outcomes.** The v1 comparison halted because one
  long synchronous request timed out with no usage record. A batch is submitted
  once and its results are retrieved later, each with its own usage. A result
  without complete usage is still treated as unknown and halts the stage.
- **Lower cost.** Both OpenAI and Anthropic currently price batch requests at
  about half the synchronous rate. Recheck on the execution date.
- **Equal treatment of arms.** All runs advance round by round together. A
  stage halt leaves every run truncated at the same round, rather than
  finishing some conditions and leaving others unstarted, as happened in v1.
- **No order effects.** Because all runs execute concurrently, randomized
  condition order within blocks is no longer needed. Request order within each
  batch is randomized and recorded instead.

Each batch request carries the ledger's attempt ID as its custom ID. The ledger
reserves every request in a round before the batch is submitted, and settles
each result by ID. A request missing from the results, expired, or errored
without usage is unknown usage. Rounds take longer in wall-clock time: a
provider may take minutes to hours per batch. That is acceptable because no
result is time-sensitive.

## Stages and gates

Each stage needs the owner's approval. A failed gate ends the proposal with a
reported result, not a redesign under the same approval.

### Stage 0: implementation, verifier and target selection (no inference)

- Build the changes under [Required changes](#required-changes).
- Cross-check the verifier against known codes: the ternary Golay code
  [11, 6, 5] and its extension [12, 6, 6] over GF(3), and the hexacode
  [6, 3, 4] over GF(4).
- Profile the verification limit on k.
- Take and commit the dated table snapshot, then apply the selection rule.

**Gate:** the verifier reproduces every known code exactly, and at least six
targets qualify. Otherwise switch to the fallback task.

### Stage 1: positive control (offline)

Algorithmic agents that may change only their assigned polynomial slot. Isolated
agents cannot assemble a full code beyond their slot; shared agents can combine
slots through the archive.

**Gate:** the shared arm beats the independent arm on every target in each of
10 seeds. Failure means the instrument is broken.

### Stage 2: algorithmic 2×2 (offline)

All five arms with seeded algorithmic agents implementing the four strategies,
30 seeds per arm per target, at matched simulated token budgets.

**Gate:** S-D beats I-H, ranked by (d, fewer minimum-weight codewords), in at
least 20 of 30 seed-paired comparisons, pooled across targets by majority.

Passing does not predict model behavior. It rules out a design in which even
programmed agents gain nothing from sharing on these targets.

### Stage 3: live calibration and model selection (paid, baseline arm only)

Stage 3 runs only the I-H baseline, so comparing models here reveals nothing
about any treatment effect. It selects the Stage 4 model by a rule fixed before
any call, and measures per-call tokens and cost.

**Candidates:**

| Model | Price per million tokens (input / output) | Why it is a candidate |
| --- | --- | --- |
| OpenAI `gpt-5.6-terra` | 2 / 12 (2026-09-09 snapshot) | Reference. The only model with evidence in this repository: 94 live calls, one malformed response, no refusals, one transport timeout. |
| Claude Sonnet 5.5 (`claude-sonnet-5-5`) | 2 / 10 | Similar price, strict structured outputs, adjustable reasoning effort. |
| Claude Haiku 5.5 (`claude-haiku-5-5`), optional | 0.10 / 0.50 | Cheap enough for many more blocks, if it can make progress on the task. |

Prices are synchronous list prices on the date shown and must be reverified
on the execution date. Each candidate uses medium reasoning effort, the same
prompts and schema, and strict structured output. No candidate may use
automatic fallback to another model.

**Procedure:** two I-H runs per candidate at the same per-run allowance, on
targets drawn from the frozen target list, through the batch path.

**Disqualification.** A candidate is disqualified by any of:

- a response that fails the action schema;
- a result without complete usage;
- a refusal;
- a returned model identifier that differs from the requested one.

**Selection among the remaining candidates:**

1. Keep candidates whose baseline makes real progress: in both runs, the final
   best code improves on that run's first valid code, and neither run reaches
   the snapshot's upper bound.
2. Choose the one with the lowest observed cost per decision.
3. If none qualify, stop and report. Do not relax the rule after seeing results.

The selected model's observed tokens per decision set the Stage 4 per-run
allowance: enough for at least eight decisions per agent at the observed 90th
percentile, plus one reservation. The number of blocks is then set by the
approved Stage 4 budget, with a minimum of 10.

Stage 3 needs its own ceiling, proposed after Stage 2. At 200,000 tokens per
run, two runs per candidate cost roughly USD 1–2 for `gpt-5.6-terra` or
Sonnet 5.5 at batch rates, and under USD 0.10 for Haiku 5.5.

### Stage 4: live comparison (paid)

Five arms × at least 10 blocks, so at least 50 runs. One model, selected in
Stage 3. Zero retries. All runs execute concurrently through per-round
batches. Each block uses one target; targets rotate across blocks.

**Decision rule for "coordination materially helped":** S-D beats I-H, ranked
by (d, fewer minimum-weight codewords), strictly in at least 8 of 10 blocks.
Under no effect that has probability 56/1024 ≈ 0.055 (one-sided sign test).
Ties count as losses. If Stage 3 sets more than 10 blocks, the threshold is the
smallest number of wins whose one-sided sign-test probability is at most
0.055, fixed in the manifest before Stage 4 starts. If the rule is not met, the report states that no
material benefit was detected at this scale. It does not claim the effect is
absent.

**Illustrative magnitude only, not a request.** The halted live studies spent
about three-quarters of their tokens on output, giving a blended rate of about
USD 9.6–9.9 per million tokens for `gpt-5.6-terra`. Applying the same output
share to the other candidates, 50 runs at 200,000 tokens each (10,000,000
tokens) would cost roughly:

| Model | Synchronous | Batch (about half) |
| --- | ---: | ---: |
| `gpt-5.6-terra` | USD 96 | USD 48 |
| Claude Sonnet 5.5 | USD 81 | USD 40 |
| Claude Haiku 5.5 | USD 4 | USD 2 |

Tokenizers and verbosity differ between models, so treat these as ±50%. Since
runs end when their allowance is used, actual spend will be close to these
figures, less about 25,000 tokens of final reservation per run. The actual
ceiling is proposed after Stage 3.

## Outcomes

**Primary (methods):** best verified code per run, ranked by (d, fewer
minimum-weight codewords).

**Primary (mathematics):** any verified code that beats the snapshot's lower
bound for its target. It is reported regardless of arm.

**Secondary:**

- tokens to reach the I-H arm's median final result;
- quality against cumulative tokens, with budget stops marked;
- invalid actions, decisions per agent and stopping reasons.

**Reuse, measured structurally:** accepted codes whose base was another
agent's archive entry, and whether that lineage reached the run's best code.
Reuse alone is not evidence of benefit.

**Not measured: emergent organization.** Strategies are assigned, so any
specialization is prescribed. See [Deferred](#deferred).

## Record submission and disclosure

The October 2026 objections concern transparency, verification and credit.
Any improved code will be handled as follows:

- verified independently, outside the run, with a second implementation or
  standard software before any claim;
- submitted to the table maintainer through their process, stating that it was
  found by AI agents in a controlled experiment;
- released with the generator, prompts, model and version, token and cost
  totals for the whole study, and every run including failures;
- not announced publicly before the maintainer accepts it.

## Stopping rules

- Unknown usage, an unexpected returned model or service tier, or an
  ambiguous dispatch halts the stage and keeps its reservation. For batches,
  this includes a request missing from the results, an expired request, an
  error without usage, and a batch the provider does not complete within its
  stated window.
- A refusal is a failed decision for that agent, recorded with its usage. It
  is never rerouted to another model.
- Zero retries. Failed runs stay in the denominator; missing quality is never
  counted as zero.
- No transfer of unspent allowance, no replacement runs, no continuation after
  a halt without fresh authorization.
- One-use authorization per stage, enforced durably as in `feedback_campaign`.

## Required changes

| Area | Change |
| --- | --- |
| Task interface | Move task specifics out of `runtime.py` behind an interface (validate, reconstruct, describe, reference). Add `swarm_lab/tasks/qc_codes.py`; keep the 3-AP task as the regression task and add discrepancy-2 as the fallback. |
| Verifier | GF(3) and GF(4) arithmetic, quasi-cyclic generator construction, exact minimum distance and minimum-weight count. Cross-check against known codes. |
| Reference data | A dated, committed snapshot of the target entries with source URLs. |
| Runtime | Team-wide and private archive conditions, archive limits, per-agent strategy, base-plus-change actions with runtime-recorded provenance, tokens as the binding budget. No coordinator. |
| Limits | Raise `context_bytes` for archives. Relax the `m ≤ 24` checks in `RunConfig.validate()` and `cli.verify_replay()` only for the regression task's scope. |
| Provider | Strategy prompts of equal length and the new action schema. An Anthropic adapter alongside the OpenAI one, built only if a Claude model remains a Stage 3 candidate; it must report refusals and usage in the ledger's terms. |
| Batch transport | Submit one batch per round with attempt IDs as custom IDs; poll for completion; settle results by ID; treat missing, expired or usage-less results as unknown. Round-snapshot scheduling, used offline as well. |
| Ledger | Batch pricing in the frozen price snapshot, reserving a whole round before submission. The ledger currently excludes batch pricing because it had no reservation model for it. |
| Policies | Four algorithmic strategies and the slot-restricted positive-control agent. |
| Campaign | Manifest, frozen target draw, block-to-target assignment, recorded request order and one-use authorization, following `feedback_campaign.py`. |
| Analysis | Paired comparisons, the sign test, quality-versus-token curves and structural reuse counts. |

## What this can and cannot show

**Can show:** whether sharing verified stepping stones beats best-of-N at equal
tokens on lightly contested open records, with one model and four agents, and
whether any benefit depends on strategy diversity. It may produce a verified
record.

**Cannot show:** generality across tasks, models or team sizes; that a
specific archive entry caused an improvement; that agents organized themselves;
or that model agents beat specialized search software. A record, if found,
would not by itself show that coordination was needed to find it.

## Deferred

- **Full-history sharing arm**, to test whether naive sharing underperforms a
  curated archive.
- **Checkpoint-and-fork** to attribute benefit to specific archive entries
  (see the [experiment protocol](experiment-protocol.md)).
- **Emergent organization:** identical, unassigned agents over long runs, with
  pre-registered measures compared against shuffled-label null models.
- **Program search** on cap sets with sandboxed code execution.
- **Verification as the coordinated task:** agents independently checking
  whether formal statements match their papers. The October 2026 release made
  this bottleneck visible, but grading it needs a ground-truth set first.

## Suggested approval wording for the first step

> Approve Stage 0 and Stage 1 of the coordination v0.3 proposal: implement the
> task interface, code verifier, table snapshot and target selection, archive
> conditions and positive control, and run the offline positive control. No
> model requests and no API spending. Stage 2 and later stages require separate
> approval.

This text is a proposal for the owner to approve. Its presence in the
repository is not approval and does not permit a model request.

## Sources

Reviewed 2026-10-10. Items marked *preprint* or *reported* were not
independently verified for this proposal; recheck before freezing the protocol.

- OpenAI manuscripts: <https://github.com/openai/math>; coverage at
  [Engadget](https://www.engadget.com/2279815/openai-just-posted-hundreds-more-results-on-major-math-problems/)
  and [The Decoder](https://the-decoder.com/some-mathematicians-call-for-openai-boycott-after-ai-generated-proofs-flood-their-field/) (reported)
- Erdős problems site changes: <https://terrytao.wordpress.com/2026/10/06/changes-to-the-erdos-problems-web-site/>
- LinCodeEvolve: <https://arxiv.org/abs/2609.37056> (preprint)
- Circle packing n=27: <https://www.cognizant.com/us/en/ai-lab/blog/self-improving-ai-agent-breaks-math-record>
- Covering repository status: <https://ljcr.dmgordon.org/cover.html>
- Ramsey lower bounds with AlphaEvolve: <https://arxiv.org/abs/2603.09172> (preprint)
- Discrepancy C=2 maximum 1,160: <https://arxiv.org/abs/1402.2184>; multiplicative maximum 246: <https://arxiv.org/abs/1407.2510>
- Wang et al., Reasoning in Token Economies: <https://arxiv.org/abs/2406.06461>
- Single agents at equal thinking budgets: <https://arxiv.org/abs/2604.02460> (preprint)
- Kim et al., Towards a Science of Scaling Agent Systems: <https://arxiv.org/abs/2512.08296>
- CORAL: <https://arxiv.org/abs/2604.01658> (preprint)
- CodeEvolve: <https://arxiv.org/abs/2510.14150> (preprint)
- Learning to Share: <https://arxiv.org/abs/2602.05965> (preprint)
- Station: <https://arxiv.org/abs/2608.23691> (preprint)
- Multi-agent failure modes (MAST): <https://arxiv.org/abs/2503.13657>
