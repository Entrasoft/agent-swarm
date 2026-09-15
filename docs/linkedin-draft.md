# LinkedIn companion — unpublished draft

We built a small agent swarm to see whether useful cooperation would emerge: one agent finding something another could challenge, extend, or combine into a better result.

Our inspiration was OpenAI's reported Navier–Stokes result. Its account described roughly 10,000 concurrent agents in the group that produced the result. Our pilot used at most four agent states, taking turns. It was a small experiment in coordination, with different tools, tasks, and operating conditions. [OpenAI's account](https://openai.com/index/navier-stokes-solution/)

We chose a modest mathematical task with independently checkable answers: find a large integer set containing no three distinct numbers in arithmetic progression. An exact solver handled our instance in milliseconds. Our purpose was to inspect how agents worked together.

One trace captures the distinction we encountered. A message reached another agent, the recipient reported using it, and the next verified candidate matched the shared candidate. Information traveled. That step produced no improvement.

Both our comparison and a smaller feedback follow-up stopped prematurely. An unresolved request left usage uncertain, triggering our rule to halt the entire campaign. Neither campaign exhausted its budget.

But repetition was visible before those stops. In the follow-up, the observed worker receiving attempt history submitted the same eight-member set eight times. Relaxing the stopping rule would permit more observations; it would not guarantee progress.

We established neither a cooperation advantage nor evidence that cooperation cannot work. Four constrained agents also cannot tell us what happens at the scale of OpenAI's reported effort.

The useful lesson is about experimental design: we could check answers and trace messages, but our interface offered limited ways to develop and reuse intermediate work. Whether a richer environment would help remains untested.

We are pausing paid experiments and publishing the evidence and limitations.

[Read the article and inspect the MIT-licensed code](https://github.com/Entrasoft/agent-swarm/blob/main/docs/article-draft.md)
