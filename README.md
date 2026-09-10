# Agent Swarm Lab

**Four Agents, One Checkable Problem: When Does Coordination Help?**

Current laboratory version: **0.2.0**. The completed integration pilot remains version 0.1.1. See the [changelog](CHANGELOG.md).

An inspectable Python laboratory for testing multi-agent orchestration against a precisely checkable problem: find a largest subset of `{1, …, m}` with no three distinct members `a < b < c` such that `a + c = 2b`.

The offline runtime, validator, hidden exact evaluator, durable usage ledger, local desktop viewer, and tests are implemented. **Algorithmic runs use seeded search, not LLM reasoning.** Scripted runs are explicit protocol demonstrations. The opt-in live adapter completed a [three-call Terra pilot](docs/terra-pilot.md): 2,260 provider-reported tokens, USD 0.016160 calculated API cost, and a verified optimum at m=12. This is an integration check. The later [live comparison](docs/live-comparison-results.md) halted as prescribed after 95 attempts because one request had unresolved usage: ten runs started and ten remained unstarted. Known usage is 156,639 tokens and USD 1.499658; these are incomplete totals. No started run reached the exact m=24 optimum.

The subsequent [v0.2 solo feedback qualification](docs/feedback-v02-results.md) also halted, after 32 attempts. Its feedback progress criterion was unmet. All six planned rows are preserved; three never started. Known usage is 65,225 tokens and USD 0.644390, with a separate reservation held for one unresolved request. The studies remain inconclusive about coordination and feedback effectiveness.

## Offline quickstart

Python 3.11 or later. The runtime and tests use the standard library; no API key or package installation is needed from the checkout.

```sh
git clone https://github.com/Entrasoft/agent-swarm.git
cd agent-swarm
python3 -m venv .venv
. .venv/bin/activate
python -m unittest discover -s tests -v
python -m swarm_lab run --m 12 --agents 4 --condition independent --steps 24 --out runs/quickstart
python -m swarm_lab replay runs/quickstart --verify
```

Each run requires an empty output directory. Use a new directory for another run. `--steps` limits total team decisions, including coordinator decisions; `--agents` counts the coordinator when present. `m` is the mathematical universe size, independent of agent count.

Optional editable installation: `python -m pip install -e .` provides the `swarm-lab` command. It may need network access to install build tooling; the commands above do not.

## Display and experiments

```sh
python -m swarm_lab run --m 12 --agents 10 --condition adaptive --steps 48 --out runs/adaptive
python -m swarm_lab view runs/adaptive
python -m swarm_lab run --mode scripted --steps 8 --out runs/scripted
python -m swarm_lab benchmark --sizes 10,12,18,24 --seeds 0,1,2 --steps 48 --out runs/campaign
python -m swarm_lab oracle --m 24
```

The viewer is a **local Tk desktop application**, requiring a Python installation with Tk and a graphical session. It shows real recorded events and can follow an active run. Pause, step, scrub, or replay; inspect public payloads and provenance. No website is deployed. See [display instructions](docs/display.md).

![Actual local replay display](docs/images/display.jpg)

Independent workers receive no peer findings or global incumbent. Fixed and adaptive teams each contain one coordinator and `N−1` searchers. Fixed routing is a coordinator star; adaptive algorithmic routing uses a disclosed heuristic. The deterministic scheduler and verifier do not count as agents. Scheduling is bounded and offline execution is reproducible for fixed settings; live completion order can vary.

The exact evaluator runs after workers stop, outside their observations. Candidate validation establishes a lower bound; only independent evaluation can tighten the upper bound. A run is marked solved only when those bounds meet. The deterministic solver is extremely fast on these small instances; this is an orchestration laboratory, not evidence that agents outperform ordinary algorithms.

## What is counted

Each attempted provider request has one durable SQLite ledger entry. Input/output totals include their cached/reasoning subsets; subsets are never added again. Estimates, provider-reported usage with calculated prices, and billing-reconciled charges remain separate. Missing usage is unknown and retains a conservative reservation. Retries share the run ceiling; duplicate telemetry does not duplicate spend. Request admission uses atomic token and decimal-currency reservations.

Offline accounting uses a frozen **simulated fixture**, dated 2026-09-09, with rates of $1 uncached input, $0.25 cached input and $2 output per million tokens. These are test rates, not provider prices. Offline runs have zero actual model calls and zero marginal model API spend; local compute still takes time. [The hand-auditable fixture](examples/usage-fixture.json) includes successful, retried and unresolved attempts.

Each run saves `config.json`, `events.jsonl`, SQLite stores, `summary.json`, `usage-ledger.json`, `usage-ledger.csv`, and `usage-summary.json`. Ledger exports include per-agent/purpose/model/call groups, latest cumulative accounting, raw usage metadata, frozen prices and correction records. Full generated runs are ignored by Git. The viewer's time curves use recorded usage events; ledger timelines explicitly represent latest accounting in dispatch order.

## Optional live provider

The adapter uses the [OpenAI Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create), checked on 2026-09-09. It offers a narrow candidate/message schema, with no hosted tools or arbitrary code execution. Secrets come from `OPENAI_API_KEY` in the process environment or a protected local `.env`; credential contents and authorization headers are never recorded. Run `python3 -m swarm_lab.credentials setup` in an interactive Terminal to enter the key at a hidden prompt.

Live mode requires **all** of `--mode live`, `--allow-live`, `--model`, `--price-file`, `--token-limit`, and `--cost-limit`. There is no default live model. A nonsecret Terra price snapshot is supplied and must be reverified on the run date. See [Terra setup and the bounded pilot command](docs/live-provider.md) before an explicitly budgeted run. The owner's authorization for the completed pilot covered three calls, USD 2 and 100,000 total tokens; it does not extend to further runs.

## Evidence and design

- [Halted v0.2 qualification: results and all six planned rows](docs/feedback-v02-results.md), with [public evidence and reproduction](examples/terra-feedback-v02/README.md)
- [v0.2 solo feedback protocol](docs/feedback-v02-protocol.md), [budget proposal](docs/feedback-v02-budget-proposal.md), and [approved execution record](docs/feedback-v02-execution.md)
- [Results and reproducible commands](docs/results.md)
- [Completed Terra pilot and public trace](docs/terra-pilot.md)
- [Authorized difficulty calibration protocol](docs/calibration-protocol.md)
- [Completed difficulty calibration and m=24 selection](docs/terra-calibration-results.md)
- [Interrupted live comparison: results, costs and all twenty planned rows](docs/live-comparison-results.md)
- [Approved four-condition live comparison protocol](docs/live-comparison-protocol.md) and [original proposal](docs/live-comparison-proposal.md)
- [Architecture](docs/architecture.md) and [predefined experiment protocol](docs/experiment-protocol.md)
- [Claims and evidence](docs/claims-evidence.md)
- [Article working draft](docs/article-draft.md) and [LinkedIn draft](docs/linkedin-draft.md), unpublished
- [Original handoff](docs/codex-swarm-lab-handoff.md), describing the broader intended project

Checkpoint/fork causal interventions and empirical claims of emergent or effective cooperation remain future work. The message-withholding prototype is not a causal experiment. See the protocol for the required leakage controls.

The separately approved solo difficulty calibration at m=18 and m=24 is complete: six calls, 10,395 tokens and USD 0.102580 calculated cost, with zero retries. m=18 was first-call optimal; m=24 retained a verified gap of two and was selected by the frozen rule. `python3 -m swarm_lab.calibration prepare` freezes a protocol and shared ledger without API requests; `execute --allow-live` is guarded against repeating this completed authorization.

The owner approved the m=24 comparison on 2026-09-09: five repetitions each of solo, independent, fixed and adaptive, with up to twelve total calls per run. Its separate ceilings are 240 calls, USD 20 and 2,000,000 tokens, preallocated as twenty equal twelve-call, USD 1 and 100,000-token allowances. Zero retries and a persistent execution claim prevent automatic repeat runs. Follow the [execution protocol](docs/live-comparison-protocol.md); an unknown charge or ambiguous dispatch halts the campaign. That execution has now halted and must not be restarted under this authorization. The remaining reservation is 28,075 tokens and USD 0.3076875; billing is not reconciled. [Public evidence](examples/terra-comparison) includes all twenty rows, charts and an independent audit. Preparation makes no API calls, but does not grant a fresh execution:

```sh
python3 -m swarm_lab.comparison prepare --price-file configs/gpt-5.6-terra-price.json --out runs/terra-comparison
```

## v0.2 feedback qualification

The [solo feedback qualification](docs/feedback-v02-results.md) halted after **32 attempted calls**: one run completed, one failed on the local action protocol, one was interrupted by a transport timeout with unknown usage, and three never started. The treatment received repeated-attempt history on seven decisions without improving its verified best; the qualification criterion was **unmet**. One observed pair with unequal completion cannot establish a feedback effect or swarm advantage. [Public evidence](examples/terra-feedback-v02/README.md) preserves every planned row, traces, charts, replay checks and the independent audit.

This study compares a private-best-only baseline with a worker that also receives up to eight of its own recent attempts and deterministic validator feedback. Both arms use the new `feedback-v0.2` decision protocol: invalid mathematics consumes a decision and can be followed by another; provider or protocol failures stop the run, and unknown usage retains its reservation. The existing default `legacy` protocol preserves the previous stopping behavior.

The owner approved **six runs, 72 calls, USD 6 and 600,000 tokens**, with zero retries. Known usage is **65,225 tokens and USD 0.644390 calculated cost**; the unknown request retains **28,077 tokens and USD 0.3076925**. These are incomplete measured totals and a separate reservation, with billing unreconciled. The `feedback_campaign` module enforces a one-use authorization, which is now consumed; see the [execution record](docs/feedback-v02-execution.md). No automatic continuation is authorized. The original preparation module below remains a proposal generator with no execution command, spending ledger or credential access.

```sh
python3 -m swarm_lab.feedback prepare --out runs/feedback-v02-proposal
python3 -m swarm_lab run --mode scripted --condition solo --agents 1 --concurrency 1 --max-retries 0 --steps 12 --decision-protocol feedback-v0.2 --memory-mode history_feedback --out runs/feedback-offline
python3 -m swarm_lab replay runs/feedback-offline --verify
```

The scripted command is an offline wiring demonstration with a repeated fixed candidate; it supplies no model-effectiveness evidence. Fault-injection tests cover mathematical repair, history isolation and bounds, malformed responses, refusals, timeouts, and unknown-usage holds. Replay reconstructs the v0.2 worker's visible history from verified submissions. Live dispatch now records a client correlation ID before the request and retains sanitized structural diagnostics; IDs do not guarantee execution, cancellation or idempotency. See the official [request-ID guidance](https://developers.openai.com/api/reference/overview#supplying-your-own-request-id-with-x-client-request-id).

Historical evidence and its source hashes remain unchanged. When auditing v1 from this newer checkout, supply its frozen source revision using the instructions in the [public evidence package](examples/terra-comparison/README.md).

## License

[MIT](LICENSE). Copyright © 2026 Christopher Deschenes.
