# LinkedIn companion — unpublished draft

**Our small swarm experiment did not establish an advantage from cooperation.** Agents exchanged results and reported using one another's contributions, but we could not show that working together improved their answers.

We asked agents to find the largest subset of the numbers 1 through 24 containing no three evenly spaced numbers. We chose it because every candidate could be checked independently and preliminary model attempts left room for improvement. An exact solver established in milliseconds that the largest valid set contained ten numbers, giving us a clear measure of progress.

The comparison recorded 27 delivered messages and 20 reports of reuse. None of the ten started runs reached the known optimum. Only five of twenty planned runs completed, leaving the comparison inconclusive.

We had set out to see whether useful cooperation would emerge: one agent finding something another could challenge, extend, or combine into a better result.

Our inspiration was OpenAI's reported Navier–Stokes result, involving roughly 10,000 concurrent agents in the successful group. Our comparison used at most four agent states, taking turns under very different conditions. [OpenAI's account](https://openai.com/index/navier-stokes-solution/)

One trace made the distinction concrete: a recipient reported using a colleague's message, then submitted the same candidate. Information traveled; that step produced no improvement.

Both our comparison and a smaller feedback follow-up stopped prematurely. An unresolved request left usage uncertain, triggering our rule to halt the entire campaign. Neither campaign exhausted its budget.

But repetition was visible before those stops. In the follow-up, the observed worker receiving attempt history submitted the same eight-member set eight times. Relaxing the stopping rule would permit more observations; it would not guarantee progress.

These incomplete studies cannot establish that cooperation fails, or that a larger swarm would succeed.

The useful lesson is about experimental design: we could check answers and trace messages, but our interface offered limited ways to develop and reuse intermediate work. Whether a richer environment would help remains untested.

We are pausing paid experiments and publishing the evidence and limitations.

[Read the article and inspect the MIT-licensed code](https://github.com/Entrasoft/agent-swarm/blob/main/docs/article-draft.md)
