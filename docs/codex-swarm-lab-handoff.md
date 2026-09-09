# Codex handoff: Ten Agents, One Checkable Problem

You are implementing a small, inspectable multi-agent research laboratory and preparing the evidence for an accompanying Substack article and LinkedIn post. Work in the current repository; inspect applicable instructions and existing code before editing. If no project exists, create a clean local project named `swarm-lab`. Make routine implementation decisions autonomously. Build and run the offline vertical slice first; do not stop at an architecture proposal.

## Purpose and audience

The owner, Chris, has a BS in Math/Physics, an MS in Electrical Engineering, and experience building applied AI and distributed systems. He worked with agent concepts in the late 1990s. The article should connect that history to current LLM agents without presenting agents, negotiation, evolutionary computation, or distributed problem solving as new inventions.

Central question: When does communication among small numbers of model-driven workers improve verified problem-solving enough to justify its cost?

Secondary questions: How should we initially size the team? How do we distribute and adapt work? Can workers choose useful collaborations and divisions of labor that were not assigned in advance? How can we distinguish communication, influence, and beneficial cooperation?

This is a teaching experiment, not a claim of novel mathematics or a reproduction of a frontier laboratory's infrastructure. Negative results are valuable. A deterministic solver may outperform every LLM configuration; report that honestly.

## Mathematical task and independent ground truth

For configurable integer m, find the largest subset S of {1,...,m} with no three distinct members a < b < c satisfying a+c=2b. Only arithmetic progressions are forbidden. For example, {1,2,4} is valid, although it is geometric; {1,2,3} is invalid.

Start with m around 10–12 for correctness and orchestration debugging. Profile before selecting larger benchmark instances, potentially up to m=24. Do not assume those sizes are difficult enough to benefit from agents. If they are trivial, report this and document a justified extension rather than silently changing the task. Distinguish universe size m from agent count N.

Implement a trusted candidate validator, checking membership, distinctness, and forbidden triples. Independently compute ground truth for tractable instances using a deterministic method. Cross-check that method against simple exhaustive enumeration on tiny cases. One possible formulation uses binary x_i and constraints x_a+x_b+x_c <= 2 for every forbidden triple, maximizing sum x_i. If using a solver, distinguish feasible, optimal, timed-out, and infeasible statuses and record its version.

Keep evaluation ground truth inaccessible to solving agents. A valid candidate establishes a lower bound L; only a sound independent procedure establishes an upper bound U. Initially U=m is valid. Stop as solved only when verified U=L. Otherwise report best-found, gap, and stopping reason. A model assertion, successful bounded test, or passing candidate check is not an optimality proof. Do not put an exact oracle in the workers' toolset and then credit the resulting lookup to collective discovery.

## Minimal architecture

Use Python, asynchronous execution, typed structured messages, a small durable event/artifact store, and a configurable provider interface. Prefer standard libraries and few dependencies over a large orchestration framework. Read current official API documentation when implementing a live provider; never assume a model ID from this handoff.

Separate these layers:

1. Deterministic runtime: state transitions, queueing, concurrency, budgets, retries, persistence, and cancellation.
2. Agent policy: receives a scoped observation and proposes a tool call, candidate, task request, message, or completion.
3. Shared artifacts: versioned claims, candidates, assumptions, evidence, failures, and dependencies.
4. Trusted verification and hidden evaluation.
5. Display and replay: projections of recorded events, not invented activity.

An agent is a logical stateful decision unit, not necessarily an OS process or a distinct model. Keep private context and a mailbox per agent. Worker count, in-flight model-call count, and model choice must be independently configurable. Do not describe separate contexts as statistically independent reasoning.

Implement three explicitly labeled execution modes:

- Scripted replay: predetermined events for UI and protocol checks; no inference or emergence claims.
- Algorithmic workers: real deterministic or seeded search policies to exercise allocation and verification without credentials. This is a running computation, but not LLM reasoning.
- Live LLM workers: real model calls and tool use with recorded usage. Never silently fall back to scripted output and present it as live.

Use existing credentials only through supported secret mechanisms. Never log secrets or commit them. Default to offline operation. Before a paid run, obtain a concrete spend/token ceiling if none is already authorized. Missing credentials must not block the offline implementation, tests, replay, documentation, or article outline. Report estimated cost separately from actual provider usage; reserve budgets before concurrent calls to limit overshoot.

## Mandatory token and cost accounting

Token consumption and cost tracking are a core engineering discipline for this project, not optional analytics. Implement the usage ledger in the first vertical slice, before any live calls. Offline fixtures must exercise the accounting paths while clearly separating simulated usage from actual consumption.

Record one durable usage entry per provider request attempt, linked to run, agent, task, logical call, attempt, provider request ID when available, model/version, service tier, timestamps, outcome, and purpose (research, coordination, critique, synthesis, or other). Record provider-reported input and output totals and available breakdowns such as cached input and reasoning tokens. Preserve the provider's raw usage metadata, excluding secrets. Normalize provider semantics explicitly: cached tokens may already be included in input totals and reasoning tokens may already be included in output totals. Never add subset counters again. Track actual usage of system instructions, repeated history, tool results, and peer messages when they enter model requests; a local message delivery itself is not an additional model charge. Attribute context components only as estimates unless the provider exposes exact accounting.

Separate three concepts: pre-call estimated tokens/cost, post-call provider-reported usage with calculated cost, and billing-reconciled charges when available. Missing usage is unknown, never zero. Include failed, retried, cancelled, and timed-out attempts, retaining unresolved possible charges. Count every real attempt once; replaying logs or receiving duplicate telemetry must not duplicate spend. Make ledger writes durable across restarts, with explicit estimated/observed/reconciled status and correction records. Use decimal or integer currency units for financial aggregation.

Maintain a versioned price configuration with provider, exact model/tier, currency, rate units, effective/retrieved dates, and official source URL. Verify rates against official documentation when configuring a live run. Freeze the price snapshot with each run; historical estimates must not silently change when current rates change. Handle cached input, cache writes/storage, batch or other tier differences, and billed tools only when applicable. When uncached input, cached input, and output are disjoint billing buckets priced per million tokens, calculate cost as (uncached_input*input_rate + cached_input*cached_rate + output*output_rate)/1e6, then add applicable non-token charges. Use the actual provider's billing rules rather than forcing every provider into that formula. If prices are unavailable, report tokens and an unpriced cost component, not a fabricated total.

Expose aggregate input/output tokens, available cache/reasoning subsets, known estimated spend, unresolved charges, committed budget, and remaining budget per call, agent, purpose, model, and run. All research, coordinator, critic, summarizer, and retry calls share the same run ceiling. Keep marginal API spend separate from local compute time and any explicitly modeled infrastructure cost. Offline mode has zero actual model calls, not zero total resource use. Export machine-readable JSON and CSV ledgers and a concise run summary. Provide a cumulative tokens/cost timeline and per-agent breakdown in the display; show measured versus estimated status clearly.

Enforce configurable total-token and currency ceilings with atomic reservations before dispatching concurrent calls. Reserve conservatively using input estimates, configured maximum generation, applicable billable reasoning allowances, and any bounded tool charges. Admit no new work without sufficient uncommitted budget. Reconcile reservations when usage arrives; retain conservative reservations for ambiguous pending charges. Bound automatic retries and include them in admission control. Report any overshoot and why it occurred; do not promise absolute billing control if provider-side activity cannot be bounded or cancelled. Budget exhaustion must save the run and stop gracefully. Already authorized ceilings persist; do not repeatedly ask for permission within them.

Evaluate verified progress per million tokens, cost to verified optimality, and cost per verified solution across the full campaign, including unsuccessful runs in the spend numerator. Report no-success cases as undefined/no successes, never zero cost per success. Include quality-versus-cost curves and the fraction of spend used by coordination and retries. For different models, equal tokens need not mean equal dollars: label matched-token, matched-cost, and matched-time experiments separately. Do not claim efficiency from a denominator that omits coordination or failed attempts.

Acceptance checks must cover rate arithmetic, token subset normalization, cache handling, missing usage, duplicate telemetry, retry attribution, restart recovery, concurrent reservation enforcement, and agreement of per-call and aggregate totals. Include a hand-auditable offline fixture with expected totals. The README and article must explain what was counted, price dates, and remaining billing uncertainty.

## Team and communication conditions

Make N configurable, initially 1, 4, and 10. Define N as all model-driven decision agents, including a coordinator when present. Deterministic schedulers and verifiers do not count. Document exact role allocation for each condition.

Provide these conditions:

- Solo baseline with the same relevant tools and comparable total model budget.
- Independent workers whose results are collected without cross-worker information sharing.
- Fixed coordination with predefined roles and routing.
- Adaptive peer coordination: at N=10, one coordinator and nine workers may choose tasks, recipients, and roles within the protocol.

For the independent condition, prevent accidental information sharing through a common incumbent, artifacts, summaries, or coordinator messages. Keep infrastructure telemetry available to the experimenter while withholding it from workers when it reveals others' findings. To isolate recipient choice, also compare fixed and adaptive routing with otherwise matched team composition.

The protocol should support a minimal vocabulary such as request_help, propose_claim, submit_candidate, challenge_claim, share_artifact, and report_result. Leave content, recipient, and timing open in the adaptive condition. Enforce visibility, delivery, message-size, and budget rules. Avoid all-to-all broadcast by default. All accepted knowledge retains provenance and assumptions.

Suggested event fields: run_id, event_id, parent_event_ids, timestamp, actor, recipient, event_type, task_id, artifact_id/version, model/version, usage, and verification_status. Separate message delivery from actual downstream use. A read event alone is not evidence of causal contribution.

## Assignment and optimization

Start with a simple round-robin or fixed-budget baseline. Then implement a transparent exploratory allocation heuristic. A possible priority is estimated verified progress plus an exploration bonus divided by estimated cost. The verified gap U-L is a useful outcome, but rewards can be delayed: retain exploration capacity for tasks that unblock other work.

Label the heuristic as experimental. Do not claim gradient descent or classical bandit guarantees for a discrete, dependent, changing task environment. Distinguish evolutionary search over candidate solutions from merely distributing tasks. Evolutionary selection/mutation/recombination is an optional later extension, not required for the first working system.

Enforce bounded queues and context sizes, task leases or equivalent ownership, duplicate-delivery handling, finite retries, failure reporting, and cancellation on completion or budget exhaustion. Avoid arbitrary agent-generated code execution on the host. Begin with a narrow approved toolset; add sandboxed code execution only if the environment provides a genuine isolation boundary. A subprocess alone is not a security sandbox.

## Graphical display

Build a local display that can show live runtime events and replay saved runs. Select the simplest supported delivery mechanism in the working environment and follow any applicable website skills if building a website. Do not deploy publicly.

Show the team graph with actor identities, current tasks, and states. Distinguish assignment edges, peer messages, artifact references, and verification events. Include an aligned activity timeline, current verified bounds, usage/budget, and stopping reason. Clicking an event or artifact should expose its public message/tool payload, assumptions, verification status, and provenance chain. Do not expose or fabricate private chain of thought.

Support pause, step, and replay. Preserve stable node positions for readability. Scripted demos and algorithmic/live runs must be conspicuously labeled. Avoid a fabricated 'emergence score.' A connected graph does not demonstrate cooperation.

## Evaluation and claims

Predefine the experimental matrix and metrics before examining comparative results. Run small offline smoke experiments first; expose a bounded benchmark command for larger campaigns. Do not automatically launch the entire paid matrix.

Measure verified solution quality, optimality gap, time to verified optimality when reached, total tokens, elapsed time, tool/verification compute, message overhead, invalid claims, duplicate work, and artifact reuse. Count coordinator and summarization calls in the same budget. Include a deterministic-solver baseline and all failed/timed-out runs. Match tools and budgets for causal comparisons. Report fixed-time comparisons separately from fixed-budget comparisons.

Repeat across seeds and tractable instance sizes. Record prompts, settings, code revision, scheduling choices, provider versions, and raw events. Explain that seeded model calls may not guarantee exact reproducibility. Report distributions and uncertainty with limitations appropriate to sample size; do not claim statistical significance from a handful of runs.

Define adaptive communication as unassigned recipient/timing choices; emergent organization as unassigned recurring specialization or collaboration; effective cooperation as improvement in verified outcomes under controlled comparison. These are distinct.

Design a checkpoint/fork intervention to deliver versus withhold a selected message. Prevent the same information leaking through shared artifacts or summaries; keep comparable remaining budgets and repeat continuations. Treat trace-based attribution as suggestive until an intervention supports it. Do not reward influence alone: persuasive errors can spread. General improvements across a test set matter more than one impressive anecdote.

## Repository and documentation deliverables

Deliver a small, coherent repository with install/run instructions, config examples, .env.example without credentials, tests, labeled example traces, architecture documentation, experiment protocol, and results reporting. Propose an appropriate license for the owner's selection rather than silently publishing under one. Keep generated bulky runs out of version control by default.

Test mathematical validation, tiny-instance oracle agreement, visibility separation, budget enforcement under concurrency, invalid claim rejection, task completion/cancellation, and event replay consistency. Focus tests on consequential behavior. Include a copy-pasteable offline quickstart that you have actually executed. Make no 'one command' claim until it works in a clean supported environment.

Prepare an article package:

- Substack draft, approximately 1,800–2,500 words once evidence exists.
- LinkedIn companion, approximately 200–350 words, with a clear reason to inspect the repo.
- A short claims-to-evidence register, separating historical sources, architectural choices, hypotheses, observed results, and limitations.
- Real diagrams/screenshots derived from the implementation and actual traces; label illustrative graphics.

Working title: 'Ten Agents, One Checkable Problem: When Does Coordination Help?'

Editorial arc: Chris's 1990s agent perspective; what LLMs change; a precisely checkable problem; architecture and protocol; assignment and budgets; live observations; controlled comparisons; what cooperation means; what failed; reproducible next steps. Use concrete engineering prose. Do not invent first-person experiences, discoveries, quotes, or results for Chris. Before live evidence exists, produce the conceptual sections and a clearly marked results outline, not a completed empirical success story. Do not imply a small finite problem is new mathematical research. Consider later held-out task variants to reduce answer-recall effects, but disclose changes and revalidate ground truth.

Starting historical/methodological sources to read and verify before citing:

- Reid G. Smith, The Contract Net Protocol (1980): https://www.eecs.ucf.edu/~lboloni/Teaching/EEL6788_2008/papers/The_Contract_Net_Protocol_Dec-1980.pdf
- Auer, Cesa-Bianchi, Fischer, Finite-time Analysis of the Multiarmed Bandit Problem (2002): https://cesa-bianchi.di.unimi.it/Pubblicazioni/ml-02.pdf
- Jaques et al., Social Influence as Intrinsic Motivation for Multi-Agent Deep Reinforcement Learning: https://arxiv.org/abs/1810.08647

The discussion was inspired by a reported OpenAI Navier–Stokes effort. Independently verify any such contemporary claim against primary sources before including it; distinguish announcement, proof scope, formalization, and independent acceptance. Do not treat earlier conversational descriptions or a reconstructed diagram as authoritative evidence of OpenAI's internal architecture. The article should stand on its own without that hook.

## Execution order and completion report

1. Inspect the workspace and record the smallest viable plan.
2. Implement and test the mathematical validator and hidden oracle.
3. Run the offline event-driven vertical slice with configurable workers and budgets.
4. Add replay/display, then fixed versus adaptive communication controls.
5. Add the live provider behind explicit configuration and a bounded usage policy.
6. Run the authorized experiment subset; preserve raw data and failures.
7. Prepare the evidence-backed documentation and article package appropriate to the results actually available.

Proceed on all unblocked work. Keep implementation, empirical results, and editorial claims synchronized. At completion report exactly what ran, what passed, measured outcomes, remaining uncertainties, commands to reproduce, and the next bounded live experiment if it could not run. Do not publish posts, deploy publicly, or push a new public repository without explicit authorization.
