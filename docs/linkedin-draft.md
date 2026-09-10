# LinkedIn companion — unpublished draft

A four-agent comparison stopped before it answered whether communication helped. The stopping point became part of the result.

Agent Swarm is a small public Python laboratory with an independently checkable task: find the largest subset of {1, …, 24} containing no three distinct numbers in arithmetic progression. The exact optimum is ten. Workers never receive the evaluator's answer.

The plan compared solo search, four independent searchers, fixed coordination and adaptive peer routing. Twenty runs shared explicit ceilings, with coordinator calls included and zero retries.

What actually happened:

- Ten runs started: five completed, four failed and one was interrupted. Ten remain unstarted.
- All started runs found valid sets of eight or nine members. None reached ten.
- Ninety-five requests were attempted. The 94 responses with known usage accounted for 156,639 tokens and USD 1.499658 calculated cost.
- One transport failure left usage unknown, so the protocol halted the campaign. Its reservation remains held; total cost is incomplete and billing unreconciled.

This is an interrupted descriptive study, not evidence that a particular team structure wins. The deterministic evaluator's median time was about 8.47 milliseconds on this host—an essential baseline beside the model results.

The useful artifact is inspectable evidence. Follow a delivered message into a worker's actual observation, check its next candidate, and see what the ledger counted. Delivery and reported use do not establish causal benefit. The report retains failures and every missing row.

The next engineering work concerns failure diagnostics and unresolved accounting. The coordination question remains open.

[Inspect the results, traces and MIT-licensed code](https://github.com/Entrasoft/agent-swarm/blob/main/docs/live-comparison-results.md)
