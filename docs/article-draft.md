# What Two Interrupted Agent Experiments Taught Us About Testing Cooperation

**Publication deferred September 15, 2026. Retained as an unpublished project record.**

The draft below preserves the previous narrative, including its former publication
plan. It is not being prepared for release. See the [current decision](publication-notes.md)
and [research watch](research-watch.md).

We began with a simple curiosity: could we build a small agent swarm and watch useful cooperation emerge? We wanted agents to build on one another's discoveries, challenge weak ideas, and find complementary ways forward. A modest experiment, with every interaction visible, seemed a practical place to start.

Our inspiration was OpenAI's reported Navier–Stokes solution. Its September 8 announcement described roughly 10,000 concurrent agents in the successful group, using an internal model and research tools. Researchers also guided the effort and consolidated intermediate findings. OpenAI released a proof writeup and a Lean formalization. Those are OpenAI's reported results; our project does not independently assess the proof. [OpenAI's account](https://openai.com/index/navier-stokes-solution/)

We built something much smaller: four agent states sharing twelve sequential model calls. Two interrupted studies later, we can trace messages and check proposed answers, but we cannot establish that cooperation improved performance. The experience exposed limitations in how we had framed and operated the experiment.

## A small, checkable question

Our mathematical task was to find the largest subset of the integers 1 through 24 containing no three numbers in arithmetic progression. For example, {1, 2, 4} is valid; {1, 2, 3} is not. A deterministic validator checked every submitted candidate. A separate exact solver established the optimum of ten, without revealing it to the workers.

This was a coordination test fixture, not a mathematical breakthrough. The exact solver's median recorded time was about eight milliseconds on the experiment's host. [Measured baseline](live-comparison-results.md#usage-and-conventional-solver-baseline) We chose the problem because answers were independently checkable and preliminary calibration left room for the models to improve. [Calibration record](terra-calibration-results.md)

The comparison had four configurations: one persistent searcher, four isolated searchers, a coordinator with three searchers communicating through it, and the same team with more flexible routing. Every run had the same twelve-call allowance, including coordinator work. Each member of a four-agent team therefore had at most three decisions; the solo worker had twelve.

The live model was gpt-5.6-terra. Workers retained their best candidate and, where permitted, received messages. They had no code-execution or research tools. Their output was a candidate set and an optional structured message. Roles were assigned. This gave us controlled information boundaries, but only a narrow representation of research activity. Equal allowances also did not guarantee equal actual token use or spending.

## One interaction, examined closely

The most informative example was a short trace selected by a reproducible rule: the first message delivery in the earliest adaptive run, followed through its receiver's first valid submission.

| Recorded step | What happened |
| --- | --- |
| A colleague shared a result | The coordinator sent an eight-member candidate and requested help. |
| The recipient could see it | The exact message appeared in the recipient's observation. |
| The recipient reported using it | The response identified the message as used. |
| The answer was checked | The recipient submitted the same eight-member set. The team's best remained eight. |

The record establishes delivery, visibility, and reported use. It does not establish that the message helped, caused repetition, or prevented improvement. Across the started coordinated runs, we recorded 27 deliveries and 20 reports of reuse. Those counts alone cannot demonstrate beneficial cooperation. [Annotated trace](../examples/terra-comparison/report/trace-annotations.md)

That distinction matters for anyone evaluating agents. A busy conversation is easy to observe. Establishing that one participant's contribution improved another's work requires a stronger test, including comparisons that control what information is available.

## Why the studies stopped

The first comparison planned twenty runs. Ten started: five completed, four failed, and one was interrupted. After 95 attempted requests, a transport failure left one request's usage unknown. Our declared rule halted the entire campaign. All started runs reached valid sets of eight or nine members; none reached ten. [Full comparison](live-comparison-results.md)

We had deliberately made spending control conservative. Requests reserved an allowance before dispatch, and uncertain usage remained reserved. But we also made accounting uncertainty a campaign-wide stop condition. The experiment ended with substantial budget remaining.

The partial traces showed repetition, so we tried a smaller follow-up: could a solo worker make better use of its own attempt history and validation feedback? Six runs were planned. Three started before another request timed out, again leaving usage unknown and stopping the campaign.

The sole observed history-and-feedback treatment submitted the same eight-member set eight times before a local protocol failure. Both observed baseline workers improved from eight to nine; one completed and the other encountered the timeout. The treatment's predeclared progress criterion was unmet, but this small, incomplete comparison cannot establish that feedback harmed performance. [Follow-up results](feedback-v02-results.md)

The known calculated API subtotals were approximately $1.50 for the comparison and $0.64 for the follow-up. Each excludes an unresolved request; complete costs remain unknown and billing is unreconciled. These figures also exclude development and local computing effort. Detailed accounting belongs in the linked reports, alongside every failed and unstarted row.

Our rigid rules explain the interrupted evidence. They do not explain away the repetition already observed, or imply that additional calls would have produced progress. In hindsight, we would distinguish a failed request from a reason to abandon an entire study, while retaining conservative spending reservations and explicit failure limits. That is a proposed engineering change, not a result we tested.

## What our scale could tell us

OpenAI's reported group was orders of magnitude larger than ours. Agent count was only one difference: model capability, tools, research duration, and human guidance also differed. Our brief, interrupted comparison cannot establish whether the kind of cumulative research described in that account would develop at our scale. Neither account establishes a minimum number of agents required for useful cooperation.

There was another mismatch with our original ambition. We imagined researchers passing along partial discoveries, methods, and objections. Our interface largely asked them to exchange candidate sets and short assumptions. That constrained what they could contribute, although we did not isolate its effect on performance.

A future design could deliberately encourage collaboration through shared research notes, peer checks, and requests for help when progress stalls. We might call that **encouraged emergence**: prescribe opportunities for interaction while leaving partnerships, specialization, and ways of combining results open. Required interaction would be engineered behavior; any claim of emergent organization would need additional evidence.

Choosing a different mathematical problem might make such contributions easier to express. Doing so merely because this experiment disappointed us would risk changing the question in search of a favorable result. Changing the task, tools, communication rules, and scale together would also obscure which change mattered.

## Publishing what we learned

Our immediate objective is an article, and we are pausing further paid experiments. The existing evidence gives us no basis for high confidence that another small campaign would produce beneficial cooperation.

We can still publish something useful: a transparent account of a system that verified answers, preserved interactions, and revealed limitations in its own experimental design. We learned to distinguish communication from demonstrated benefit, to treat failure handling as part of study design, and to examine whether the workspace supports the contributions we hope to observe.

The [MIT-licensed repository](https://github.com/Entrasoft/agent-swarm) preserves the protocols, executed source revisions, and evidence. The [detailed study account](study-account.md) retains the full tables and accounting; the [claims register](claims-evidence.md) separates observations from interpretation. Readers can inspect and replay the saved evidence without another model request.

We set out to watch cooperation emerge. We ended with a clearer understanding of what our experiment could measure—and why the question we cared about remains unanswered.
