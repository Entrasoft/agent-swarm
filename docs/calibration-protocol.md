# Terra difficulty calibration protocol v1

Prepared and authorized on 2026-09-09. Commit this protocol and the implementing
source before sending the first calibration generation request. Record the
commit and source hashes in the campaign artifacts. Any change after inspecting
an outcome must be a dated amendment that identifies the inspected evidence.

This is a small difficulty calibration for a later practitioner article about
the cost and benefit of coordination. It is separate from the completed m=12
[Terra pilot](terra-pilot.md), whose first call found the optimum, and from the
[offline campaign](experiment-protocol.md). Preserve those historical protocols
and raw artifacts unchanged. Calibration is not a swarm comparison.

## Authorized scope

The owner approved the following new stage; unused headroom from the original
pilot is not part of this authorization:

> Up to six Terra calibration calls across m=18 and m=24, with a combined USD 2
> and 100,000-token ceiling, zero retries. Stop when either ceiling prevents
> another call.

The call ceiling counts every attempted generation request, including failed,
incomplete, timed-out and malformed responses. It includes all purposes, not
only successful search decisions. There are no auxiliary model calls. No paid
comparative campaign, replacement attempt or later model run is authorized by
this document. Completion or a stopping condition ends this stage; remaining
headroom does not permit another stage.

## Fixed execution plan

| Order | Task size | Condition and roles | Maximum decisions |
| --- | ---: | --- | ---: |
| 1 | m=18 | Solo, one searcher | 3 |
| 2 | m=24 | Solo, one searcher | 3 |

Use `gpt-5.6-terra`, medium reasoning effort, the default service tier, a maximum
of 25,000 output tokens per request including reasoning, a 120-second request
timeout, zero automatic retries and concurrency one. Run the two sizes in the
fixed order shown. Keep the existing task, prompts, validator, context limits,
candidate feedback and seed default unchanged. Record all effective settings,
including the seed, rather than implying that a seed controls provider sampling.

The [model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-terra),
[standard pricing](https://developers.openai.com/api/docs/pricing) and
[cache accounting](https://developers.openai.com/api/docs/guides/prompt-caching)
were rechecked on 2026-09-09. The frozen rates remain USD 2 ordinary input,
USD 0.20 cache reads, USD 2.50 cache writes and USD 12 output per million tokens.
The pre-run full-output reservation bounds are 28,106 tokens and USD 0.307765
per m=18 call, and 28,130 tokens and USD 0.307825 per m=24 call. All six maximum
reservations sum to 168,708 tokens and USD 1.846770. This exceeds the token
ceiling: six calls are possible only if earlier usage settles below its maximum
headroom. The runner must stop when the next reservation cannot fit; it must
not lower output headroom or raise the approved ceilings to force completion.

Each size starts with a fresh private context. Within a size, later decisions
may see the worker's earlier candidate through the existing observation format.
There are no peers, coordinator messages, hosted tools or shared incumbents.
Do not transfer the first size's candidates, evaluation, summaries or usage into
the second worker's context.

Workers search for a large subset of `{1,...,m}` containing no three distinct
members `a < b < c` with `a+c=2b`. Independently validate every submitted
candidate. The exact evaluator runs only after that size's worker phase; its
result and candidate do not enter a worker observation or improve the worker's
lower bound. Do not stop a size early because the experimenter recognizes an
optimal candidate. Three decisions are planned unless admission control or a
failure stops work.

Prepare the shared campaign after committing the protocol and source, then
execute the same prepared campaign:

```sh
python3 -m swarm_lab.calibration prepare \
  --price-file configs/gpt-5.6-terra-price.json \
  --out runs/terra-calibration

SSL_CERT_FILE=/etc/ssl/cert.pem python3 -m swarm_lab.calibration execute \
  --allow-live \
  --out runs/terra-calibration
```

Preparation records the immutable manifest, both run
configurations, protocol snapshot, source hashes and official same-day price
snapshot before generation. The runner fixes the authorized ceilings above;
command defaults cannot expand them. Execution requires an explicit live opt-in
and exclusive markers that prevent running the campaign a second time. A fixed
authorization claim under the repository's ignored `runs/.authorizations/`
directory spans all output directories; preparing another output directory does
not grant another execution. These local guards do not prevent deliberate
deletion or copying to a separate checkout or host. Never remove the claim to
reuse this approval. There is no generation resume after a crash. The CA-bundle setting supports certificate
verification on the original macOS host; verification remains enabled.
Credentials are supplied only by the supported local secret loader and must
never appear in commands or archived artifacts.

## Whole-stage admission and stopping

Both sizes share one durable campaign ledger. Before each dispatch, atomically
reserve a call slot, the conservative input estimate plus maximum output tokens,
and its corresponding conservative currency estimate. Admit the request only
when all three campaign limits allow that reservation. Settle it from returned
provider usage under the frozen price snapshot. Cache-read, cache-write and
reasoning counts are subsets of their inclusive input/output totals and are not
added to total tokens a second time.

Retain reservations for unknown usage, including uncertain requests after
timeouts. Keep every attempt in the ledger exactly once. A new run directory
must not create a fresh budget; a restart must not replay generation calls or
reset consumed call slots. No automatic retry is permitted. Enable the runtime's
`stop_on_failure` behavior for both sizes: stop new decisions on provider
failure, an invalid candidate or unresolved accounting, as well as budget
denial. The returned model must be exactly `gpt-5.6-terra` and the returned service tier
must be `default`; missing or different identifiers retain a conservative
reservation and stop work instead of being priced under assumed semantics.
An incomplete or failed first run prevents starting the second size;
retain its planned row as unstarted. Preserve partial artifacts and the reason
for every unattempted planned decision. An execution interrupted by a crash
remains incomplete and cannot automatically continue.

The limits govern local admission, using conservative reservations. Provider
usage can differ from estimates; a timed-out request may continue remotely.
Report any unresolved reservation, observed overage or missing usage rather than
claiming confirmed provider cancellation or billing reconciliation. Calculated
cost from provider usage is distinct from a reconciled charge. Report the
combined ledger as well as each size's contribution.

## Frozen difficulty-selection rule

Use independently verified candidate sizes and an exact evaluator result for
each size. Define `U` as the exact optimum, `L1` as the size of the first
decision's valid candidate, `Lfinal` as the best valid worker candidate after
three decisions, and final gap as `U - Lfinal`. A finite sound upper bound from
an evaluator timeout is insufficient to classify first-call saturation.

Apply the following rule only when both planned three-decision runs finish with
usable responses, valid candidates and exact evaluations, and accounting has no
unresolved attempts:

1. A size is **first-call saturated** when `L1 = U`.
2. A size is **eligible** when `L1 < U` and its final verified gap is available.
   A final gap of zero is eligible: improvement after the first call still shows
   room for search. A positive gap is also eligible; report it without assuming
   that coordination can close it.
3. Select **m=24** for the proposed comparison if it is eligible. Otherwise select
   **m=18** if it is eligible. This fixed preference does not depend on which
   size shows the larger improvement, lower cost or more appealing narrative.
4. If both sizes are first-call saturated, declare **saturation** and select no
   difficulty. Propose an overhead-focused article or a separately disclosed,
   validated task extension. Do not silently exceed the runtime's m<=24 limit.

A failed, invalid, interrupted, budget-truncated or unevaluated run makes this
stage **inconclusive** under the selection rule. Retain its observations and
attempts; do not replace it, select only the completed size, or launch substitute
runs. A further calibration would require a disclosed amendment and fresh paid
authorization. All outcomes remain in the report's attempted denominators;
missing quality is missing, not zero.

One trace per size cannot estimate success probability or establish that a task
is reliably difficult. Selection identifies a candidate for a small descriptive
comparison, not a benchmark validated across model samples. The fixed order and
the earlier m=12 observation are disclosed calibration context.

## Evidence and article consequences

Preserve the campaign manifest, frozen protocol, source revision and hashes,
effective run configurations, returned model identifiers, service tiers, all
public observations and responses, candidate artifacts, events, provider usage,
per-attempt ledgers, combined ledger, summaries and stop reasons. Collect no
private reasoning text. Independently replay both available traces and audit
combined call, token and price arithmetic without additional generation.

Report, by size and in total: planned/attempted/completed calls; first candidate
size; final `L`, exact `U` and gap; invalid and duplicate candidates; timing to
the first candidate later established optimal where applicable; worker and
evaluator elapsed times; input/output tokens and reported cache/reasoning
subsets; calculated cost; and unknown usage, retained reservations or overshoot.
Include the deterministic exact solver's result and timing as a baseline.

After calibration, apply the selection rule before drafting a separate live
comparison protocol and conservative campaign budget. The provisional comparison
is solo, four independent searchers, fixed coordination with one coordinator
and three searchers, and adaptive coordination with the same roster. The
independent-versus-coordinated contrast changes roles as well as communication;
fixed-versus-adaptive keeps the roster matched. Equal calls do not imply equal
tokens or costs. No comparative inference follows without its own explicit
authorization.

Keep calibration results separate from later comparative results. The article
may report saturation, failures or absence of coordination benefit as clearly as
improvements. A communication trace demonstrates recorded information flow,
not causal benefit. Do not infer the best model, statistically reliable task
difficulty, or a swarm advantage from this calibration.
