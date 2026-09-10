# Approved v0.2 execution record

The owner approved the [v0.2 budget proposal](feedback-v02-budget-proposal.md)
by replying “Proceed please.” to the completed preparation and its explicit
six-run, 72-call, USD 6 and 600,000-token proposal. Approval was received on
2026-09-09 in America/New_York (2026-09-10 UTC). The execution identity is
`terra-feedback-v02-2026-09-09`.

This record advances the status of the committed proposal from proposed to
approved. The original [research protocol](feedback-v02-protocol.md) and
budget text remain preserved as submitted. Their mathematical task, two arms,
schedule, settings, limits, endpoints and qualification criterion are unchanged.
No v0.2 model outcomes were inspected while preparing this execution record or
its reporting code. The later results document will identify the frozen source
commit, manifest and actual execution status.

## Exact authorized scope

Use `gpt-5.6-terra`, medium reasoning, default service tier, one solo worker on
`m=24`, twelve decisions per run, at most 25,000 output tokens per request,
120-second provider timeout, concurrency one and zero retries. Each of the six
runs has its own USD 1 and 100,000-token allowance. The shared campaign also
enforces 72 attempted calls, USD 6 and 600,000 tokens. Unused allowances are not
transferred or spent on replacements.

The ordered arms are history/feedback, private-best-only, private-best-only,
history/feedback, history/feedback, private-best-only. Each consecutive pair is
one block. Both arms use `feedback-v0.2`; invalid mathematical candidates consume
a decision and can be followed by the next scheduled decision. Known provider
or protocol failures end that run. Unknown accounting, uncertain dispatch,
unexpected model/tier, an overage or an unhandled interruption halts the campaign.
All six rows remain visible. A halt does not authorize restart or replacement.

## Price verification and execution environment

The [official Terra model page](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
confirms medium reasoning and structured outputs. The
[official pricing table](https://developers.openai.com/api/docs/pricing), retrieved
on 2026-09-10 UTC, lists standard short-context USD rates per million tokens of
2.00 ordinary input, 0.20 cached input, 2.50 cache writes and 12.00 output.
These match the proposed rates. The context cap is far below the long-context
pricing threshold. No hosted tools, auxiliary model graders or summarizers are
used.

The [new execution snapshot](../configs/gpt-5.6-terra-feedback-v02-price.json)
preserves this verification separately from the historical v1 snapshot. Dates
in this new snapshot use UTC. Run preparation and execution with `TZ=UTC`, so
the daily price check uses that same date basis. `effective_date` records when
these rates were verified as applicable, not a claim about when OpenAI first
introduced them. If execution has not begun on that UTC date, reverify and freeze
the new snapshot before dispatch. Once execution begins, do not alter its inputs.

Use the host's `/etc/ssl/cert.pem` trust bundle for Python HTTPS, with normal
certificate verification enabled. The credential is loaded locally by the
existing protected credential loader; it never appears in commands, committed
files, manifests, events or diagnostic text.

## Freeze, execute once, preserve

The separate `feedback_campaign` module supplies execution. The older
`feedback prepare` command remains a non-executable proposal generator.

Before paid inference, commit the implementation, tests, these documents and the
price snapshot, then prepare all six UUIDs and allowances. The manifest includes
source hashes, the commit, full configurations, schedule, price metadata and
document text/hashes. A durable SQLite receipt binds the full manifest, including
run identities and descriptive fields. Real execution requires a clean source
checkout matching the committed preparation.

```sh
TZ=UTC python3 -m swarm_lab.feedback_campaign prepare \
  --price-file configs/gpt-5.6-terra-feedback-v02-price.json \
  --out runs/terra-feedback-v02
TZ=UTC SSL_CERT_FILE=/etc/ssl/cert.pem python3 -m swarm_lab.feedback_campaign execute \
  --allow-live --out runs/terra-feedback-v02
```

The executor checks the manifest, ledger allocations and empty run paths before
claiming authorization. It creates an exclusive persistent claim in
`runs/.authorizations/` and an execution marker in the output directory. Neither
an alternate output directory nor copying a prepared manifest permits another
execution. The claim remains after success, failure or uncertainty. Do not run
the execution command again after it has claimed this authorization.

Each request reserves input and maximum-output headroom before dispatch. Client
correlation IDs are persisted before the request; server IDs, ID source, usage
counters and safe diagnostic categories are retained when available. Missing
usage retains its reserve. A reservation is not observed usage or a billing
receipt. Do not release the separate v1 unknown reservation while conducting
this study.

## Reporting commitment

Publish the manifest, all six planned rows, public event/usage exports,
independent replay checks and the deterministic report. Keep raw exports
separate from derived analysis. Do not publish credentials, SQLite files or
private reasoning. CSV newline normalization is permissible only with parsed
cell equality and disclosed checksums.

The report recomputes distinct valid candidates from submissions, presents
verified best size alongside diversity, and retains failures and missing data.
It records every qualifying progress event; the first in frozen execution order
is the designated explanatory witness, if any. The qualification criterion is
the one in the original protocol, not a new effect-size threshold. Observed
repair after feedback does not establish causation or a swarm advantage.

```sh
python3 scripts/report_feedback_comparison.py --campaign runs/terra-feedback-v02 \
  --out runs/terra-feedback-v02-report
```

The report command reads existing artifacts only. Optional scientific figures
may use Matplotlib. The article will distinguish this new protocol from v1 and
will not pool v1 runs as new controls. Publication in the public code repository
is authorized; the article and social-post drafts remain unpublished elsewhere.

Run the separate public audit without importing the runtime or accessing a key:

```sh
python3 scripts/audit_feedback_comparison.py runs/terra-feedback-v02
```

It checks the frozen runtime/configuration identities, six-row report, candidate
mathematics, inclusive token and cost arithmetic, retained unknown reservations
and billing uncertainty. When auditing from a later source checkout, supply
`--source-root` pointing to the recorded execution commit's source.
