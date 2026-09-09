# Ten Agents, One Checkable Problem: When Does Coordination Help?

**Unpublished conceptual draft.** The implementation and offline results live in
the repository. This text is not a completed account of live LLM collaboration.
The results section below is intentionally pending; insert only measurements
from preserved runs. Author note: add a short personally verified account of
Chris's work with agent concepts in the late 1990s before publication. No personal
anecdote or quotation has been invented here.

An animated network of agents can make a modest computation look like an
organization. One node proposes a plan, another offers a criticism, and a third
announces an answer. The activity is visible. The harder question is whether any
of those interactions made the answer better, and whether the improvement paid
for the extra work.

That question motivates this small laboratory. Give one, four or ten logical
workers the same checkable problem. Control which workers can communicate. Count
all their decision opportunities and, when actual models are involved, every
provider attempt. Then evaluate the answer independently. The aim is to make
claims about coordination inspectable, including claims that do not survive the
comparison.

## A familiar engineering problem

Agent coordination has a substantial history. Reid G. Smith's 1980 Contract Net
paper described task distribution through negotiation among nodes, with task
announcements, bids and awards. It is a useful reminder that assigning work and
controlling communication were already explicit design problems decades before
today's model interfaces. This laboratory is not a reproduction of Contract Net.
[Smith's original paper](https://www.reidgsmith.com/The_Contract_Net_Protocol_Dec-1980.pdf)

The design choice here is to let a language model eventually occupy a narrow
decision-policy slot. A policy receives a scoped observation and returns a
candidate plus an optional message. The surrounding runtime decides what may
be delivered, what counts as valid, and whether another call fits the budget.
The same interface can also hold a conventional search algorithm. That makes
it possible to debug the experiment before attributing anything to a model.

Ten workers are ten separate stateful decision units. They need not be ten
operating-system processes, and ten private contexts do not demonstrate ten
statistically independent lines of reasoning. The interesting issue is the
information each worker receives and the decisions it can make with it.

## A problem with a clear answer boundary

Choose an integer m. Find the largest subset S of {1,...,m} that contains no three
distinct members a<b<c satisfying a+c=2b. For example, {1,2,4} is allowed. It is a
geometric progression, which is irrelevant here. The set {1,2,3} is forbidden
because its three members form an arithmetic progression.

This task provides a sharp distinction between a candidate and a proof of
optimality. A validator checks that every member is an integer in the universe,
that no member repeats, and that no forbidden triple appears. A valid set of
size L establishes a lower bound. It does not establish that a larger set is
impossible.

The separate evaluator runs a deterministic exact search. If it finishes, it
provides the optimum. If it reaches its deadline, it retains a sound upper
bound U from the unfinished search frontier. Only equality U=L justifies solved
status. A confident message, several agreeing workers, or a successful candidate
check cannot close the remaining gap.

The evaluator runs after the worker phase. Its answer is not in the workers'
observations, and its own candidate never improves their reported result. That
separation matters: the experiment would answer a different question if agents
could call the exact solver and forward its output to one another.

Small instances are appropriate for catching mistakes. They may be poor tests
of sophisticated reasoning. The repository begins with m values from 10 through
24 and records a deterministic-solver baseline. If that method solves the cases
almost immediately, the article should say so. Extending the task would require
a disclosed new protocol and fresh validation, not an invisible change after
seeing uninteresting outcomes.

## Four ways to organize the work

The solo condition gives one searcher the run's decision ceiling. The independent
condition divides opportunities among multiple searchers without sharing their
findings. Their results are collected by the experimenter, but their observations
contain no shared incumbent or common summary. Even an allocator reacting to
another worker's success could leak information, so independent workers use
outcome-blind scheduling.

Fixed coordination assigns one coordinator and N-1 searchers. Searchers report
to the coordinator, which rotates its recipients. Adaptive coordination uses
the same role count but allows its policy to select message timing and a peer
recipient. In the offline implementation these selections are programmed
heuristics: share a better candidate, request help periodically, or prioritize
a peer whose reported result is weak or unknown.

Those rules are useful for exercising the protocol. They do not demonstrate
emergent organization. Roles are assigned, the search procedure is written in
Python, and the routing behavior is part of the design. A later live policy may
make different choices within the same constraints, but the evidence must come
from actual calls and preserved traces.

N counts every decision agent, including the coordinator. A ten-agent team has
one coordinator and nine searchers, not ten searchers plus free management. The
verifier and scheduler are deterministic infrastructure. Their elapsed compute
still belongs in the resource report even though they are outside N.

## A runtime that makes the boundaries visible

The implementation separates scheduling, policies, artifacts, verification and
display. Each agent has a private incumbent and a bounded mailbox. A decision
returns a candidate, at most one message, and identifiers for delivered messages
the policy reports using. Recipient rules and candidate checks run before claims
are accepted into the permitted communication path.

Tasks have one-decision ownership and finite retries. The runtime limits
concurrency independently of team size and records assignments, submissions,
verification outcomes, message delivery and completion. SQLite stores events,
artifact versions and usage entries durably. A local viewer projects that record
into a team graph and timeline; it does not invent activity to make the graph
look busy.

An edge is only an edge. Sending a message differs from delivering it. Delivering
it differs from including it in a later observation. A policy's reported use
provides provenance, not proof that the message improved the result. Clicking
through to payloads and parents helps inspect the trace, but the viewer does
not expose or manufacture private chain of thought.

Scheduling is part of the experimental condition too. The current runtime works
in bounded rounds, but offline decisions execute serially with immediate message
delivery before the next agent's observation. A round does not provide a shared
observation snapshot. Live calls can overlap, and their completion order can vary
with provider latency, so a fixed seed alone cannot guarantee the same live trace.

## Accounting before inference

The laboratory has three explicit modes. Scripted mode supplies predetermined
actions for protocol and display checks. Algorithmic mode performs real seeded
local search. Live mode uses actual provider calls and never silently substitutes
a fixture when a call fails.

The first two modes still exercise a usage ledger. Their token and currency
entries are visibly simulated. They make zero actual model calls, while consuming
real local time, storage and CPU. A simulated dollar total is a test of arithmetic
and attribution, not a claim about the cost of model reasoning.

For live calls, the ledger separates pre-call estimates, provider-reported usage
with calculated cost, and billing-reconciled charges. Every attempt has its own
identity. A retry is another attempt, while duplicate telemetry about the same
attempt must not duplicate spending. A timeout with missing usage remains
potentially chargeable; the ledger does not turn an absent number into zero.

Reservations happen atomically before concurrent dispatch. Each reserves an
input estimate and bounded output allowance against shared token and currency
ceilings. Coordinator requests, research requests and retries draw from that
same ceiling. Usage then settles the reservation, or an unresolved charge keeps
a conservative commitment. Provider activity can outlast a local cancellation,
so the implementation reports overshoot instead of promising perfect control
over billing.

The price snapshot is frozen with the run. Cached input and reasoning counters
are treated as subsets of their reported parent totals. Adding those counters
again would inflate tokens and distort comparisons. Peer messages become part
of model cost when they enter a request's context; local delivery alone is not
another model charge. Exact context attribution remains an estimate unless the
provider supplies a more precise breakdown.

## Allocation is an experiment too

The initial campaign uses round robin. Each team receives 48 total decision
opportunities, so a larger team divides the same ceiling across more private
states. This is a matched decision comparison. It does not match real tokens,
dollars or elapsed time, and those distinctions remain visible in the report.

The code also contains an experimental allocation heuristic that combines mean
verified progress with an exploration allowance and divides by estimated cost.
The exploration term reserves opportunity for work whose reward has not yet
appeared. It is excluded from the primary comparison so changing allocation does
not become another unexplained difference between communication conditions.

Auer, Cesa-Bianchi and Fischer's 2002 paper provides finite-time results for
specific bandit policies. This laboratory's dependent, changing search tasks do
not inherit those guarantees merely because an allocation formula contains an
exploration term. The formula here is an engineering hypothesis to test.
[Original paper](https://cesa-bianchi.di.unimi.it/Pubblicazioni/ml-02.pdf)

## What would count as cooperation?

Adaptive communication means recipient or timing choices were available to a
policy. Emergent organization would require recurring specialization or
collaboration that was not assigned in advance. Effective cooperation requires
an improvement in verified outcomes under a controlled comparison. These are
different claims with different evidence requirements.

Jaques and colleagues investigated rewarding causal influence over other agents'
actions in multi-agent reinforcement learning, using counterfactual reasoning.
That offers a methodological connection, not a result about this laboratory.
Here, the evaluation criterion remains verified problem-solving quality: changing
another worker's behavior can also spread a mistake.
[Original paper](https://arxiv.org/abs/1810.08647)

A stronger message-value test would fork a checkpoint just before a delivery.
One continuation receives the message, while the other does not. Both retain
comparable remaining budgets, and the same information must not leak through
another artifact, summary or paraphrased message. Repeating those continuations
across cases would make a causal claim more credible than highlighting one
attractive trace.

The current withholding option is only a diagnostic filter. It can suppress a
numbered message and repeated identical content, but it does not restore full
agent state or control semantic leakage. The sound checkpoint design is
documented as future work. No causal result should be inferred from the filter's
existence.

## Results section — pending live evidence

The offline protocol was specified before comparative analysis: four universe
sizes, three seeds, and seven combinations of condition and team size. The
preserved campaign report is the source for offline quality, gap, timing,
communication and accounting observations. Insert its findings here with the
code revision, protocol hash, attempt denominator and an explicitly algorithmic
label. Include the deterministic baseline and failures.

The initial offline campaign solved 63 of 84 runs. Every run at m=10,12,18 reached
the independently computed optimum; every m=24 run ended one member below it.
The solved/gap pattern was the same across all seven team configurations, so
these observations do not support an advantage for coordination. Review also
found that the protocol's original scheduling description did not match the
serial offline implementation. Amendment A preserves and discloses that mismatch;
the final reporting rerun is validation after inspection, not an independent
preregistered replication. See the [results record](results.md) for preserved
artifacts, revisions and final timings.

Before completing this section, report the following from authorized live runs:

- Exact model/version, prompts, settings, price dates and total ceilings.
- Verified quality and gap distributions, solved counts and stopping reasons.
- Full-campaign tokens and cost, including retries and unsuccessful attempts.
- Coordination overhead, timing and unknown or unreconciled charges.
- Controlled fixed/adaptive comparisons and evidence against the favored hypothesis.

With three offline seeds, descriptive variation is appropriate; significance
claims are not. If no configuration succeeds, cost per success is undefined.
If a deterministic algorithm dominates, that is a useful result about this
task. If communication improves a few outcomes, that is a reason for a larger
controlled test, not a conclusion about organizations of models in general.

The repository makes these decisions visible: inspect a candidate, verify its
provenance, replay the same record, and check what was counted. That is the work
needed before an interesting network animation becomes evidence about useful
coordination.
