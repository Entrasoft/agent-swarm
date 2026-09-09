# LinkedIn companion — unpublished draft

When does communication between agents improve a verified answer enough to
justify its cost?

That is the question behind Agent Swarm, a small public Python laboratory. The
task is deliberately checkable: find a largest subset of {1,...,m} containing no
three distinct terms in arithmetic progression. A trusted validator checks
candidates, while a separate exact evaluator establishes the upper bound after
workers stop. Its answer never enters their observations.

The lab compares one worker, independent workers, fixed coordination and adaptive
peer routing. A coordinator counts toward both team size and the total decision
budget. Private contexts stay separate in the independent condition.

There are three explicit modes: scripted protocol checks, seeded algorithmic
search and opt-in live model calls. The offline runs exercise real computation
and a durable usage ledger, but their model tokens and costs are simulated.
They are not evidence that LLM teams outperform a conventional solver.

The accounting includes reservations before dispatch, retries, missing usage,
cache/reasoning subsets and correction records. The local viewer shows saved
events and provenance. Message delivery, reported use and useful cooperation
remain separate claims.

This work also has a long historical context. Smith's Contract Net described
negotiated task allocation in 1980. Today's model interfaces create opportunities
to revisit familiar engineering questions with new decision policies.
[Original paper](https://www.reidgsmith.com/The_Contract_Net_Protocol_Dec-1980.pdf)

The reason to inspect the repo is practical: you can follow a candidate from
submission through verification, inspect what a worker could see, and check
exactly what the usage report counted. The protocol and limitations are included,
along with the deterministic baseline that any collaboration claim must face.

[Explore Agent Swarm](https://github.com/Entrasoft/agent-swarm)
