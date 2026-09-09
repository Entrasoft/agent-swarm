# Agent Swarm Lab

**Ten Agents, One Checkable Problem: When Does Coordination Help?**

An inspectable Python laboratory for testing multi-agent orchestration against a precisely checkable problem: find a largest subset of `{1, …, m}` with no three distinct members `a < b < c` such that `a + c = 2b`.

The offline runtime, validator, hidden exact evaluator, durable usage ledger, local desktop viewer, and tests are implemented. **Algorithmic runs use seeded search, not LLM reasoning.** Scripted runs are explicit protocol demonstrations. The live adapter is opt-in and tested with mocked responses; no paid experiment has been run.

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

The adapter uses the [OpenAI Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create), checked on 2026-09-09. It offers a narrow candidate/message schema, with no hosted tools or arbitrary code execution. Secrets are read only from `OPENAI_API_KEY` in the process environment; environment contents and authorization headers are never recorded.

Live mode requires **all** of `--mode live`, `--allow-live`, `--model`, `--price-file`, `--token-limit`, and `--cost-limit`. There is no default live model or embedded live price. See [live configuration and limitations](docs/live-provider.md) before an explicitly budgeted run. This session has authorized no paid run.

## Evidence and design

- [Results and reproducible commands](docs/results.md)
- [Architecture](docs/architecture.md) and [predefined experiment protocol](docs/experiment-protocol.md)
- [Claims and evidence](docs/claims-evidence.md)
- [Article working draft](docs/article-draft.md) and [LinkedIn draft](docs/linkedin-draft.md), unpublished
- [Original handoff](docs/codex-swarm-lab-handoff.md), describing the broader intended project

Checkpoint/fork causal interventions, a paid campaign, and empirical claims of emergent or effective cooperation remain future work. The message-withholding prototype is not a causal experiment. See the protocol for the required leakage controls.

## License

[MIT](LICENSE). Copyright © 2026 Christopher Deschenes.
