# v0.2 solo feedback pilot: budget proposal

**Status: proposed; no new paid inference is authorized or performed by this
preparation.** This is a fresh six-run qualification study under the
[v0.2 protocol](feedback-v02-protocol.md). It does not continue the halted v1
campaign or draw on that campaign's remaining authorization.

## Requested ceiling

| Scope | Planned runs | Attempted calls | Total tokens | Calculated cost ceiling |
| --- | ---: | ---: | ---: | ---: |
| Each run | 1 | 12 | 100,000 | USD 1 |
| Each arm across three blocks | 3 | 36 | 300,000 | USD 3 |
| Entire proposed pilot | 6 | **72** | **600,000** | **USD 6** |

All limits apply together. There are zero retries and no paid side calls. Each
run uses one solo worker on `m=24`, `gpt-5.6-terra`, medium reasoning and the
default service tier, with concurrency one and at most 25,000 output tokens per
request including reasoning. Both arms share twelve scheduled decision
opportunities. One arm sees only its private best; the other also sees at most
eight of its own prior attempts with deterministic validator feedback, within
the same 16,384-byte observation cap.

An invalid mathematical candidate consumes one decision in both arms and can be
followed by the next scheduled decision; there is no free repair call. Known
provider or protocol failures stop the run. Unknown usage or uncertain dispatch
halts the whole study and retains the reserve. Budget exhaustion can stop a run
before twelve calls. All six planned rows remain in the report.

## Why USD 6 rather than an expected-spend promise

The only completed twelve-call solo run in the
[halted v1 comparison](live-comparison-results.md) used **17,886 tokens and
USD 0.169622** in calculated cost. Multiplying that one observed run by six gives
**107,316 tokens and USD 1.017732**. This is transparent planning arithmetic,
not a prediction, confidence bound or permission to ignore larger costs.
The other two started solo runs ended early, and one has unresolved usage.
Do not average their incomplete totals into a full-run estimate.

The new treatment adds input history and may change reasoning length; both arms
now continue after invalid mathematics. Even the baseline therefore follows a
new protocol. The available observation does not provide a reliable distribution
of the next pilot's cost or completion rate.

The conservative reservation includes full 25,000-token output headroom. Under
the preserved short-context price snapshot, that output headroom alone costs
USD 0.30, before input. In v1, a small solo observation required roughly USD
0.3077 and 28,075 estimated tokens of request headroom. A history-bearing request
can require more. Giving each run USD 1 and 100,000 tokens leaves room to admit
later decisions after ordinary low-use settlements, while still bounding the
experiment. At large realized outputs these limits can truncate a run after
only a few calls. Equal allowances are fixed before execution and underspend
is not transferred between arms or used for replacement runs.

## Price and accounting basis

The [preserved price snapshot](../configs/gpt-5.6-terra-price.json), verified on
2026-09-09, records the following USD rates per million tokens:

| Category | Snapshot rate |
| --- | ---: |
| Ordinary input | 2.00 |
| Cached input reads | 0.20 |
| Cache-write input | 2.50 |
| Output, including reasoning | 12.00 |

These rates are a **provisional planning basis**, not a claim about prices on a
future execution date. Before live execution, reverify official model
compatibility and pricing, freeze a new dated snapshot, and check the full
proposal against it. If that changes the declared model, limits, design or
meaning of this budget, revise the proposal before approval. Do not overwrite
the historical snapshot used to audit v1.

Provider usage is the measured token source. Reasoning is a subset of output;
cache reads and writes are disjoint subsets of input. The ledger reserves before
dispatch and settles after known usage. The stated cost ceiling controls request
admission using the frozen rates and conservative estimates; if reported use
exceeds an estimate or ceiling, record the overage and halt. It is not a provider
billing control or a guarantee that an already dispatched request can be
cancelled. Calculated costs and actual billing reconciliation remain distinct.

The earlier comparison retains **28,075 tokens and USD 0.3076875** for its one
unknown attempt. That hold is not observed consumption, is not released by this
proposal, and is not folded into the new pilot's allocation. New approval would
be for an additional bounded study, with a separate campaign identity and durable
one-use authorization. No claim is made here about the account's current credit
balance or the missing request's final charge.

## What this purchases

The pilot produces six auditable rows comparing a private-best-only search loop
with the combined history-and-feedback loop. Its primary descriptive outcome is
unique valid candidates within twelve scheduled decisions; verified best size,
progress, duplicate and invalid submissions, failures, costs and timing remain
visible alongside it. The behavior gate asks whether at least one treatment run
makes verified progress after actually receiving its own prior invalid or
repeated attempt in history. It does not establish that feedback caused progress,
separate memory from feedback or measure a swarm advantage.

The prepared implementation and offline tests must pass before execution. After
approval, freeze the exact code, protocol, price snapshot, six run identities and
order before making a request. Any halt ends this authorization's automatic
execution. There is no result-dependent top-up or repeat. A negative or
unexercised outcome is still a reportable result and leads to offline revision,
not more paid calls under this proposal.

## Suggested approval wording

> Authorize the v0.2 solo feedback qualification pilot under the committed
> protocol: three paired blocks, six runs, at most 72 attempted calls, USD 6 and
> 600,000 total tokens, with twelve calls, USD 1 and 100,000 tokens per run,
> gpt-5.6-terra at medium reasoning, concurrency one and zero retries. Preserve
> failures and unstarted rows; halt on unknown usage or accounting uncertainty
> and retain its reservation. This is a new one-use authorization, not permission
> to resume or repeat the halted v1 campaign.

This text is a proposal for the owner to approve. Its presence in the repository
is not approval and does not permit a model request.
