# Changelog

## Unreleased

- Added durable shared campaign token, currency and call ceilings, plus a fixed, single-execution difficulty calibration runner. Failed or ambiguous calls stop calibration and retain reservations; returned model and service tier must match the approved configuration.
- Completed the separately authorized six-call Terra calibration: 10,395 tokens and USD 0.102580 calculated cost, with zero retries. m=18 was first-call optimal; m=24 retained gap 2 and was selected by the precommitted rule. Preserved the report and raw evidence; no swarm comparison has run.
- Added regression coverage for shared budgets, concurrent claims, returned identifiers, failure reporting and difficulty selection; the offline suite now has 125 tests.

## 0.1.1 — 2026-09-09

Marks the completed Terra integration pilot and prepares the next article experiment. This release updates package metadata and documentation; it does not change runtime behavior or perform additional inference.

- Preserves the three-call Terra pilot report and public trace: 2,260 provider-reported tokens, USD 0.016160 calculated API cost, and independently verified optimum 6 at m=12. Billing remains unreconciled.
- Adds a ready-to-paste follow-on prompt for difficulty calibration, a frozen live comparison protocol, campaign budget controls and the article package.
- Keeps the original pilot configuration, executed source revision and artifact checksums unchanged. The pilot ran at revision `eeb79d7`, before this version bump.

## 0.1.0 — initial implementation

Implemented offline search, mathematical validation, hidden exact evaluation, durable event and usage stores, a local replay viewer, an opt-in Responses adapter, secure local credential setup, and the initial evidence and article drafts. Subsequent work on this version completed the first live Terra pilot.
