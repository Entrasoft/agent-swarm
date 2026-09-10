# Proposed live comparison after Terra calibration

Status: the owner approved this proposal on 2026-09-09. The [execution protocol](live-comparison-protocol.md) records the approved scope. The [result report](live-comparison-results.md) documents its later mandatory halt; ten of twenty planned runs remained unstarted. The original proposal below is retained as planning history; its statements about missing approval are historical.

Prepared 2026-09-09 after inspecting the separately recorded difficulty
calibration. **This is a proposal, not paid authorization or an executable
campaign.** The generic comparison runner and its frozen execution manifest
still need implementation and offline validation. The six-call calibration
authorization is exhausted; no unused headroom carries forward.

## Recommended next study

Compare four configurations on **m=24**, with five repetition blocks and at most
twelve total decision calls per run. Recommend a new whole-stage ceiling of
**240 attempted calls, USD 20 and 2,000,000 tokens**, with zero retries. Allocate
each of the twenty runs the same **USD 1 and 100,000-token allowance** before
dispatch. These are maximum allowances, not spending targets or a guarantee that
all 240 decisions can complete.

The [calibration protocol](calibration-protocol.md) selected m=24 by its declared
rule. At m=18, the first candidate already had the exact optimum of eight. At
m=24, all three candidates had eight members against an exact optimum of ten,
leaving a final verified gap of two. The m=24 run used 6,486 provider-reported
tokens and USD 0.066752 calculated cost. These are observations from one solo
trace, not estimates of a stable success rate or proof that coordination will
help. The [calibration report](terra-calibration-results.md) links the preserved
evidence. Keep it separate from comparative outcomes.

## Matrix and controlled settings

| Configuration | Decision roster | Communication | Maximum calls per run |
| --- | --- | --- | ---: |
| Solo | One searcher | None | 12 |
| Independent | Four searchers | None | 12 total |
| Fixed | One coordinator and three searchers | Searchers to coordinator; coordinator chooses one searcher recipient | 12 total |
| Adaptive | One coordinator and three searchers | Each agent may choose any other permitted peer | 12 total |

Use `gpt-5.6-terra`, medium reasoning, default service tier, concurrency one,
25,000 maximum output tokens per call including reasoning, a 120-second timeout
and zero retries. Reverify official model compatibility and prices on the
execution date, then freeze the snapshot. Require the recorded returned model
and service tier to match the declared settings before pricing the response.

Keep the current system prompt, action schema, task, validator, context limits,
message limits and observation construction consistent across conditions.
Condition and role remain explicit observation fields. Each call can submit a
candidate and at most one optional message. A coordinator also submits candidates
under the same task prompt; it is not a free or exclusively managerial agent.
Coordinator candidates count toward the run's best independently valid result.

Within each four-agent run, dispatch in agent-ID order through three complete
rounds when budgets permit: each agent then receives three calls. Agent 0 is the
coordinator in fixed and adaptive. Solo receives all twelve opportunities. There
is no adaptive allocation of decision calls. A partial round can give earlier
agent IDs an extra call; preserve and report that distribution.

Sequential dispatch allows a later agent to see messages delivered by an earlier
agent before its observation is constructed. Fixed routing enforces a star but
lets the live coordinator choose its recipient and whether to send a message;
it does not implement the offline policy's rotating recipients. Adaptive routing
permits more recipient choices with the same role roster and call allocation.
Record actual messages and timing; do not infer that the model will use every
allowed route.

Each run starts with empty private contexts and mailboxes. No calibration
candidate, oracle answer, shared incumbent, other run's artifacts or earlier
comparative result enters a worker observation. Independent workers receive no
information about their peers' results, including through scheduling. The hidden
evaluator runs after the worker phase and cannot improve the reported worker
lower bound. Do not terminate calls early because the experimenter recognizes
an optimal candidate.

The independent-versus-coordinated contrast changes role composition and
communication together. Fixed-versus-adaptive has the same roster and isolates
the permitted communication policy more closely; observed model choices can
still differ in several ways. The study does not isolate the causal value of
one message or establish that a coordinator role alone improves performance.

## Why recommend USD 20 rather than USD 10?

The observed m=24 solo average was 2,162 tokens and approximately USD 0.022251
per call. Multiplying the entire three-call trace by eighty gives the following
**planning arithmetic only**:

| Quantity | Tokens | Calculated USD |
| --- | ---: | ---: |
| Observed three-call m=24 calibration | 6,486 | 0.066752 |
| Twelve calls at that same average | 25,944 | 0.267008 |
| 240 calls at that same average | 518,880 | 5.340160 |

The extrapolation is not a forecast or a confidence bound. Later reasoning,
coordinator work, message-bearing inputs and provider caching can change both
cost and token use. The three observed m=24 calls already varied substantially.

Admission must reserve maximum output headroom, not just average observed use.
At the calibration tariff, a solo request reserved about USD 0.3077 and 28,071
estimated tokens, despite settling much lower. A USD 10 campaign split equally
would give each run USD 0.50 and 50,000 tokens. Even at the observed solo average,
nine completed calls plus the next request's reservation would require about
USD 0.5079, blocking call ten. The smaller token allowance can also stop a run
before twelve decisions. That would make truncation a prominent feature of the
initial comparison.

USD 1 and 100,000 tokens per run provide more room for the unchanged output
headroom without promising full completion. At maximum output use, the proposed
limits can still stop a run after only a few calls. This study therefore compares
verified quality under equal call, token and currency ceilings, with actual
resource use reported; it is not a promise of a complete twelve-call matrix or
an experiment with exactly equal spending. Do not lower output headroom after
seeing results to force the matrix to fit.

## Order, budget fairness and stopping

Randomize condition order within each repetition block before inference and
record the realized schedule. The proposed schedule below was generated with
Python `random.Random(20260909)`, shuffling a fresh list ordered
`solo, independent, fixed, adaptive` once per block:

| Repetition | First | Second | Third | Fourth |
| ---: | --- | --- | --- | --- |
| 1 | Independent | Fixed | Adaptive | Solo |
| 2 | Fixed | Adaptive | Independent | Solo |
| 3 | Independent | Solo | Adaptive | Fixed |
| 4 | Solo | Adaptive | Fixed | Independent |
| 5 | Fixed | Solo | Independent | Adaptive |

Use repetition IDs 1–5 and recorded runtime seeds 0–4. These identifiers do not
control provider sampling or guarantee statistically independent draws. Execute
one complete scheduled run at a time. Preserve the actual order, start times
and source/runtime versions. Freeze the schedule and complete protocol before
any comparative outcomes.

Preallocate all twenty equal run allowances and enforce both run and campaign
limits through atomic durable reservations. Do not transfer underspend into a
favored condition or grant replacement calls. Every generation attempt counts,
including coordinator work, failures, invalid outputs and incomplete responses.
Maximum 240 calls includes every paid purpose; there are no auxiliary model
summaries outside this accounting.

A run stops when its next conservative reservation cannot fit. Continue the
remaining scheduled runs with their original allowances when accounting remains
known and the campaign admission checks permit it. The summed allowances fit
the whole-stage ceilings, so ordinary underspending cannot leave a later
condition with a smaller assigned budget. A failed or invalid response ends
that run without retry; retain it in the comparison.

Unknown usage, an unexpected returned model/tier, an interrupted request or
uncertain dispatch halts the entire campaign, retaining its reservation and
partial artifacts. No automatic restart or substitute output directory may
reset this authorization. Known provider usage can exceed local estimates;
report overages and stop if any aggregate ceiling prevents safe admission.
Starting a repetition block does not guarantee that all four runs finish.
Preserve completed, failed, truncated and unstarted rows in every block; do not
silently drop partial blocks or top them up. Fresh authorization and a disclosed
amendment would be needed for any later continuation.

## Analysis and article package

Report every run's best verified candidate size `L`, exact optimum `U`, gap,
solved status, stopping reason, actual attempts and completed decisions. Include
invalid and duplicate candidates, time to a candidate later established optimal,
worker elapsed time, evaluator time, message count/bytes and per-agent calls.
Missing quality remains missing; a failure is never converted to a zero gap.

For each condition, show all five planned rows, attempted denominators,
solved/attempted counts and descriptive ranges/medians for available quality
values. Explicitly label any distribution based only on runs with measurable
quality. Use the repetition blocks to organize comparisons without claiming
paired deterministic model draws or statistical significance from five runs.
Include all incurred costs and failures in efficiency calculations; cost per
solution is undefined when no run solves, and incomplete when usage is unknown.

Plot verified worker quality against cumulative provider-reported tokens and
calculated cost. Mark run endpoints, failures and budget stops; do not extend a
stopped curve as if more decisions occurred. Count all input and output tokens,
including message-bearing inputs and coordinator calls. Cache reads and writes
are disjoint input subsets, and reasoning is an output subset; do not add them
again. Report coordinator-purpose usage separately, while acknowledging that
peer content carried in searcher inputs has no exact causal cost attribution.
Distinguish calculated cost from unreconciled billing charges.

Keep the deterministic exact solver's answer and measured time visible beside
the model results. This tiny instance is easy for that solver; the study asks
about model coordination under constrained observations, not whether a swarm
beats a suitable conventional algorithm. The final article should contain a
compact comparison table, quality-versus-resource chart and annotated public
trace. Report null or adverse findings as plainly as improvements. No private
reasoning text is collected, and a trace alone is not evidence of causal benefit.

The result will be a small descriptive case study on one selected instance,
one model family and one set of settings. Difficulty selection used disclosed
calibration outcomes. Defer ten-agent scaling, model sweeps, task extensions,
adaptive call allocation and checkpoint-based interventions.

## Work required before execution

Implement the comparison runner, immutable manifest, fixed authorization claim,
equal run allocations, aggregate ledger, recorded schedule and failure handling.
Validate these paths offline, including failures, budget truncation, unknown
usage, repeat execution, concurrency and independent-worker isolation. Review
the executed routing behavior against the finalized protocol. Commit the source
and protocol, prepare conservative per-condition reservation estimates, and
provide exact executable commands before requesting any missing paid approval.

The proposed approval scope is up to 240 calls, USD 20 and 2,000,000 total tokens,
zero retries, with each of twenty runs capped at twelve calls, USD 1 and 100,000
tokens. **The owner has not approved this stage.** Writing and repository
preparation can proceed without inference; article drafts remain unpublished
until the owner approves publication.
