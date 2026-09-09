# Implementation plan — 2026-09-09

1. Establish independently tested mathematical validation and bounded exact evaluation.
2. Build an offline asynchronous runtime, durable event store and usage ledger before live access.
3. Exercise solo, independent, fixed and adaptive routing with scoped observations and bounded work.
4. Add a local desktop trace viewer, scripted replay, and bounded experiment commands.
5. Add an opt-in provider adapter, requiring explicit model, frozen price configuration and spending ceiling.
6. Run offline smoke experiments, publish raw small traces, and write evidence-aware documentation and article outlines.
7. Review the implementation, run checks in a fresh environment, then create and merge a pull request.

Public repository and pull request creation/merging are authorized. MIT was selected by the owner. The initial implementation preceded any paid-run authorization. The owner subsequently authorized one three-call Terra pilot with USD 2 and 100,000-token total ceilings; that [pilot is complete](terra-pilot.md). The owner has now separately approved [difficulty calibration](calibration-protocol.md): at most six calls across m=18 and m=24, with combined USD 2 and 100,000-token ceilings, zero retries. That stage is complete; the frozen rule selected m=24, with 10,395 tokens and USD 0.102580 calculated cost. The owner subsequently approved the [m=24 comparison](live-comparison-protocol.md), with separate ceilings of 240 calls, USD 20 and 2,000,000 tokens across twenty equal run allowances and zero retries. API credentials must come from the environment or a protected, Git-ignored local secret file; they must never enter configuration artifacts, logs, source, or commits.
