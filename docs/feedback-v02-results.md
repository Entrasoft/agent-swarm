# Solo feedback v0.2: preserved partial results

The qualification study halted after **32 attempted calls across three of six
planned runs**. One baseline run completed twelve decisions, the treatment run
ended on a local action-protocol failure, and the second baseline run ended with
unknown usage after a transport timeout. Three runs never started. The declared
feedback qualification criterion was **unmet**: the treatment received records
of its repeated attempts but never improved its verified candidate size.

Known usage totals **65,225 tokens and USD 0.644390 calculated cost**. The final
unknown request retains **28,077 tokens and USD 0.3076925** in reservations.
Total usage and calculated cost remain unknown, and billing is unreconciled.
The authorization was executed once and remains claimed. There were no retries,
replacement calls, transfers of unused allowances or continuation after the
halt. Resolving the unknown charge alone would not authorize another call.

## Frozen design and execution

The owner approved the [six-run proposal](feedback-v02-budget-proposal.md) on
September 9, 2026 in America/New_York, corresponding to September 10 UTC. The
[execution record](feedback-v02-execution.md) records that approval separately
from the preserved [research protocol](feedback-v02-protocol.md). Implementation,
protocol, execution record, price snapshot and reporting logic were committed at
[`d86c9c38ba0d8a283423087f13fe148d88253b94`](https://github.com/Entrasoft/agent-swarm/commit/d86c9c38ba0d8a283423087f13fe148d88253b94)
before inference, through [PR #8](https://github.com/Entrasoft/agent-swarm/pull/8).
The offline suite contained 236 passing tests; GitHub checks passed before
dispatch.

The [manifest](../examples/terra-feedback-v02/manifest.json) binds campaign
`terra-feedback-v02-5fd7b15a-79a3-4df5-8362-a5b07d96e852`, all six run UUIDs,
their configurations, source hashes, document text and price snapshot. It was
prepared at 03:43:06.926 UTC on September 10. The first run started at
03:45:31.714 UTC; the halt was finalized at 04:49:02.784 UTC. These are wall-clock
timestamps; the timing discrepancy below prevents treating their difference as
measured model execution time.

Both arms used one solo worker seeking the largest subset of integers 1 through
24 with no distinct three-term arithmetic progression. Both used
`gpt-5.6-terra`, medium reasoning, the default service tier, twelve scheduled
decisions, a 25,000-token maximum output allowance including reasoning, a
120-second request timeout, concurrency one and zero retries. Each run had
100,000 tokens and USD 1; the shared ceilings were 72 attempted calls, 600,000
tokens and USD 6. No budget-admission stop occurred.

The baseline saw its own verified private best. The treatment additionally saw
up to eight of its own attempts and deterministic validation results, within
the same 16,384-byte observation cap. Both arms used the same system prompt and
the same rule allowing the next scheduled decision after invalid mathematics.
Neither had peer messages, oracle feedback, auxiliary model calls or a hidden
conversation chain. The exact evaluator ran after each worker phase and could
not contribute candidates to the worker result. This study combines memory and
feedback; it does not separate their effects. Earlier pilots and the halted v1
comparison are historical context, not additional controls.

## All six planned rows

The primary outcome is the number of distinct valid sets actually submitted,
deduplicated across the entire run. Initial private state does not count.
Completed decisions below are candidate verifications, including invalid
mathematics; a paid request rejected before candidate verification still counts
as an attempted call. `L` is the best verified worker size; the hidden evaluator
established `U=10` for each started run. None reached that optimum. Unstarted
outcomes remain missing.

| Order | Block / arm | Status | Calls / verified decisions | Unique valid | Valid / duplicates / invalid math | First valid L → final L | Gap | Known tokens | Known calculated USD |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| 1 | [1 / history-feedback](../examples/terra-feedback-v02/r01-history_feedback/summary.json) | failed: protocol | 9 / 8 | 1 | 8 / 7 / 0 | 8 → 8 | 2 | 13,063 | 0.101086 |
| 2 | [1 / private-best-only](../examples/terra-feedback-v02/r01-private_best_only/summary.json) | completed | 12 / 12 | 2 | 10 / 8 / 2 | 8 → 9 | 1 | 26,924 | 0.278098 |
| 3 | [2 / private-best-only](../examples/terra-feedback-v02/r02-private_best_only/summary.json) | interrupted: unknown usage | 11 / 10 | 2 | 9 / 7 / 1 | 8 → 9 | 1 | 25,238† | 0.265206† |
| 4 | 2 / history-feedback | unstarted | — | — | — | — | — | — | — |
| 5 | 3 / history-feedback | unstarted | — | — | — | — | — | — | — |
| 6 | 3 / private-best-only | unstarted | — | — | — | — | — | — | — |

† Incomplete subtotal: the unknown final request is excluded from known usage,
but its reservation remains committed. Its unknown amount is not zero.

There were **30 candidate verifications: 27 valid and three invalid**. The 27
valid submissions included **22 duplicates within their respective runs**. The
treatment's three planned primary values are `[1, missing, missing]`, with an
observed range of 1–1. The baseline's are `[2, 2, missing]`, with an observed
range of 2–2. These ranges describe the available observations only.

| Block | Treatment unique sets | Baseline unique sets | Treatment − baseline | Availability |
| ---: | ---: | ---: | ---: | --- |
| 1 | 1 | 2 | −1 | Both started; treatment failed, baseline completed |
| 2 | — | 2 | — | Treatment unstarted; baseline interrupted |
| 3 | — | — | — | Both unstarted |

Block one is the only pair with both runs observed. Its difference of −1 is the
prespecified descriptive comparison under the fixed ceilings and failure rules.
It is not a pair of completed runs, a causal effect estimate, or evidence that
feedback generally reduces diversity. Provider draws were not identical; early
failures also produced unequal completed opportunities and actual spending.

## Feedback was delivered; the qualification criterion was unmet

The treatment submitted `[1,2,4,5,10,11,13,14]` eight times. It saw 36 history
entries across its nine dispatched observations, counting repeated visibility
on separate calls; no history entries were dropped. Seven observations,
decisions three through nine, contained an earlier repeated candidate attempt.
None was followed by a strict improvement in the verified best.

The [treatment trace](../examples/terra-feedback-v02/r01-history_feedback/events.jsonl)
shows the first eligible sequence directly: observation event **22** contains
the repeated second attempt, linked to verification **18**. Request **25**
dispatches that observation. Verification **29** then validates the same
eight-member set again. The report retains all seven eligible observations;
there is no qualifying progress event to select as a witness.

The criterion is therefore **unmet**, rather than unexercised: qualifying repeat
history was actually presented to the worker. Invalid-mathematics repair within
the treatment remains unexercised because that run submitted no mathematically
invalid candidate. The three live mathematical failures occurred in the
baselines, which continued under the common rule. In
[block one](../examples/terra-feedback-v02/r01-private_best_only/events.jsonl),
invalid verifications **8** and **80** were followed by later scheduled
decisions; verified size increased from eight to nine at decision five,
verification **40**. In
[block two](../examples/terra-feedback-v02/r02-private_best_only/events.jsonl),
invalid verification **24** was followed by a size-nine candidate at decision
four, verification **32**. Those workers had no attempt-history feedback, so
these are not treatment repair successes. Offline tests had already checked
continuation after invalid mathematics in both arms.

## Failures, accounting and timing

The treatment's ninth response had known usage and a completed provider
response. Local validation then emitted `invalid_action`, event **115**, with
the reason `action violates the solo feedback protocol`, ending that run as
`protocol_failure`. The retained diagnostics show HTTP 200, structured output
text, no refusal, and returned request ID
`req_e739327b7f154344971821282da94679`. The raw offending action was not retained,
and the local diagnostic does not identify which contract field failed. The
exact field-level cause cannot be reconstructed. No mathematical candidate was
credited for that ninth call. Its 1,360 reported tokens and USD 0.007710 calculated
cost remain included.

The campaign halted on block two's eleventh baseline request:

- Attempt: `94c3db77-9a8b-4309-a5b0-834b1bcc1945/task-10/attempt-0`.
- Client correlation ID, persisted before dispatch:
  `4d4d45b5-331a-436f-b914-62176c181771`.
- Request event **84**; failure event **85**; unknown-usage settlement **86**.
- Outcome `transport_unknown`; diagnostic category `transport_timeout`;
  `response_headers_received=false`; no returned provider request ID or usage.

The [raw ledger](../examples/terra-feedback-v02/campaign-ledger.json) preserves
that unresolved attempt, and the
[campaign summary](../examples/terra-feedback-v02/campaign-summary.json)
retains its reservation. All **32** attempts had persisted client IDs; **31**
returned provider IDs from response headers. There were no response-ID
fallbacks. A client ID supplies a correlation handle, not a provider receipt or
proof that an uncertain request did not execute.

Known inclusive usage is **13,831 input + 51,394 output = 65,225 tokens**.
The **50,177 reasoning tokens are already included in output**; reported cache
read and write counters were zero. Calculated cost uses the frozen rates and
includes failed attempts with known usage. The retained hold brings budget
commitments to **93,302 tokens and USD 0.9520825**, below both campaign ceilings.
Those commitments combine measured subtotals and conservative reservations;
they are not measured consumption or a billing total. Actual total cost remains
`null`, with billing unreconciled.

The final request was recorded at **03:58:08.401468 UTC** and its failure at
**04:49:02.735808 UTC**, a wall-clock separation of **3,054.334 seconds**. The
same events' monotonic elapsed counters differ by **120.036 seconds**. This
clock disagreement is preserved in the trace. The diagnostic establishes a
timeout category; these records do not identify the cause of the clock
disagreement, locate the network failure, or establish provider service latency.

Recorded worker elapsed times were **114.088**, **327.313** and **435.249
seconds**, respectively. Separate exact-evaluator times were **6.467**, **4.679**
and **7.066 milliseconds**. The evaluator found optimum ten in all three cases;
its solution is not credited to a model. These timings describe this host and
sample, with the clock limitation above; they are not a general speed comparison.

## Reproduction and claim limits

All three started runs passed replay, including reconstruction of the exact
private state and history visible on every observation. The deterministic
report passed **226** checks, and the separate public audit passed **1,065**
checks of configuration identity, candidate mathematics, token/cost arithmetic,
diagnostic linkage and retained reservations. Replay's `complete=true` records
a finalized trace; it does not mean the twelve-decision allowance completed or
the mathematical optimum was found.

The [public evidence package](../examples/terra-feedback-v02/README.md) contains
raw manifests, event and usage exports plus checksums. Derived outputs include
[analysis and all eligible exposures](../examples/terra-feedback-v02/report/analysis.json),
[all six run rows](../examples/terra-feedback-v02/report/runs.csv),
[finite measured curves](../examples/terra-feedback-v02/report/curves.json),
[independent audit](../examples/terra-feedback-v02/report/independent-audit.json)
and [replay results](../examples/terra-feedback-v02/report/replay-verification.json).
The [calls](../examples/terra-feedback-v02/report/quality-vs-calls.png),
[tokens](../examples/terra-feedback-v02/report/quality-vs-tokens.png) and
[calculated-cost](../examples/terra-feedback-v02/report/quality-vs-cost.png)
figures end at measured endpoints and label unknown subtotals. They do not
extend halted trajectories or fill missing runs with zero quality.

This pilot demonstrates that the treatment could receive its own repeated
attempts, while failing to demonstrate the prespecified recover-and-progress
sequence. It leaves only one observed pair, one treatment run and one problem
instance. It cannot establish comparative effectiveness, separate memory from
validation feedback, measure reliable failure rates, or support a swarm
advantage. The adverse result and unknown request are retained. The protocol
calls for reviewing and revising the loop offline before proposing any further
paid stage; this halt supplies no authority for additional sampling.
