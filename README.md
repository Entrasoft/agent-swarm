# Agent Swarm Lab

**Ten Agents, One Checkable Problem: When Does Coordination Help?**

A planned small, inspectable research laboratory for measuring when communication among model-driven workers improves verified problem solving enough to justify its cost.

## Status

This repository currently contains the project brief and implementation plan. No runtime, benchmarks, live model experiments, or empirical results have been implemented yet. Requirements in the brief describe intended behavior, not existing capabilities.

The initial problem is to find a largest subset of `{1, …, m}` containing no three distinct members `a < b < c` with `a + c = 2b`. A trusted validator and separate deterministic evaluator will keep candidate validity distinct from proof of optimality.

## Planned implementation

1. Build and test the candidate validator and a hidden exact oracle, cross-checked against tiny exhaustive cases.
2. Implement an offline Python runtime with durable events, scoped agent observations, and token/currency reservations and usage accounting.
3. Add deterministic worker policies and clearly labeled scripted replay, then a local event display.
4. Compare solo, independent, fixed-coordination, and adaptive-routing conditions under explicit budgets.
5. Add an explicitly configured live provider after verifying API documentation and prices. A concrete paid-run ceiling is required before live experiments.
6. Publish reproducible offline evidence and prepare editorial drafts with observed results separated from hypotheses.

See [the full handoff](docs/codex-swarm-lab-handoff.md) for the proposed architecture, acceptance checks, experimental controls, and editorial scope. Historical links in that brief are leads to verify before citation.

## Research standards

- Keep evaluation ground truth inaccessible to solving workers.
- Label scripted, algorithmic, and live execution separately.
- Count coordination, retries, and unsuccessful calls in experiment costs.
- Report negative results and unresolved optimality gaps.
- Treat communication traces as observations, not proof of beneficial cooperation.

## License

A license has not been selected. MIT is a proposed option for the owner's consideration; no license grant is made by this proposal.
