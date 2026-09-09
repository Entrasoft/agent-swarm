# Claims-to-evidence register

Prepared 2026-09-09. Historical sources were fetched and checked against primary
papers on this date. This register separates source-backed history, implemented
design, hypotheses and measured evidence. Drafts are unpublished; no live success
claim is authorized by an offline trace.

| Claim | Classification | Evidence and permitted wording | Limits |
| --- | --- | --- | --- |
| Negotiated task allocation predates modern LLM interfaces | Historical | Smith, December 1980, describes task announcements, bids and awards in distributed problem solving. [Original paper](https://www.reidgsmith.com/The_Contract_Net_Protocol_Dec-1980.pdf) | The lab is not a Contract Net reproduction; do not claim the general agent idea was invented in 1980. |
| Exploration/exploitation has rigorous analyses in specified settings | Methodological history | Auer, Cesa-Bianchi and Fischer, 2002, prove finite-time results for defined bandit policies. [Original paper](https://cesa-bianchi.di.unimi.it/Pubblicazioni/ml-02.pdf) | No transferred guarantee for this lab's dependent tasks or experimental allocation formula. |
| Counterfactual influence has been studied in multi-agent learning | Methodological history | Jaques et al. reward influence over other agents' actions in their MARL setting. [Original paper](https://arxiv.org/abs/1810.08647), initially 2018, revised 2019 | Their results do not demonstrate benefit in this repository; influence is not our success metric. |
| Chris worked with agent concepts in the late 1990s | Author-supplied background | Supplied project handoff | Have Chris supply or approve any personal account. No invented first-person anecdote, quotation or discovery. |
| The validator checks the specified finite task | Implementation | [math_task.py](../swarm_lab/math_task.py), [mathematical tests](../tests/test_math_task.py) | Candidate validity establishes only a lower bound. Arithmetic progressions are forbidden; geometric progressions alone are allowed. |
| The exact evaluator agrees with tiny exhaustive enumeration | Observed test result | Targeted mathematical tests executed successfully for m=0..12 | This tests the implementation on finite cases; it is not a proof that tests eliminate every defect. |
| The exact solver is very fast at current benchmark sizes | Preliminary measurement | Initial local m=24 profile: optimum 10, 8,621 search nodes, approximately 4.9 ms | Machine-dependent single profile. Use preserved campaign baseline timings for formal reporting; do not present the profile as a statistical result. |
| Evaluation results are withheld from workers | Architecture | [runtime.py](../swarm_lab/runtime.py) observation constructor and evaluator call after worker phase | A code boundary, not a host sandbox; policies have no arbitrary code-execution interface. |
| Independent workers cannot share findings through observations | Architecture plus acceptance check | Runtime omits global incumbent/artifact access; policy ignores mailboxes in solo/independent; outcome-blind allocation; visibility tests | Separate contexts are not statistically independent reasoning. Keep the allocator outcome-blind. |
| Fixed and adaptive have matched team composition at each N | Architecture | One coordinator plus N-1 searchers in both modes; [protocol](experiment-protocol.md) | Current comparison changes recipient and timing rules together. Roles are assigned. |
| Adaptive offline behavior is algorithmic | Implementation | [policies.py](../swarm_lab/policies.py) contains explicit seeded heuristics | It is not live inference, emergence, learned specialization or an evolutionary algorithm. |
| Every paid request attempt belongs in the same budget | Engineering requirement and implementation | [ledger.py](../swarm_lab/ledger.py), runtime reserve/settle boundary and ledger acceptance tests | Calculated cost is not a billing statement; unresolved usage and provider cancellation limits remain visible. |
| Offline accounting has zero actual model calls | Mode definition; confirm in each run | Runtime's algorithmic/scripted branches and exported summary/ledger | Simulated token/currency values are not model consumption; real local compute is excluded from marginal API spend. |
| The live Terra integration completed three authorized calls within its ceilings | Observed pilot result | [Pilot report](terra-pilot.md) and [raw trace](../examples/terra-pilot/events.jsonl): 2,260 tokens, USD 0.016160 calculated cost, zero retries, verified optimum 6 at m=12 | One solo integration check with two duplicate candidates; no coordination comparison, billing reconciliation, or model-selection conclusion. |
| m=24 is eligible for a proposed coordination comparison under the calibration rule | Observed calibration result | [Six-call calibration](terra-calibration-results.md): m=18 first-call optimum 8; m=24 first and final size 8 against exact optimum 10. Combined 10,395 tokens and USD 0.102580 calculated cost | One trace per size; selection was predeclared. This does not establish reliable difficulty or that coordination will improve quality. |
| More communication improves quality | Hypothesis | Requires the preregistered campaign and later matched live comparisons | No supporting conclusion follows from an attractive graph, greater message count or one successful run. |
| The first offline matrix compares 84 attempts | Protocol | Four m values × three seeds × seven conditions; [protocol](experiment-protocol.md) | Actual completion, failures and outcomes must be read from the campaign record, not inferred from its design. |
| The initial offline campaign solved 63 of 84 runs | Observed algorithmic result | All m=10,12,18 runs solved; every m=24 run had gap 1, with the same solved/gap pattern in every condition. [Results record](results.md) | No demonstrated coordination advantage or live-model conclusion; the final reporting run is validation after inspection. |
| The initial protocol correctly specified all scheduling details | Disproved implementation-description claim | Runtime review found serial offline decisions with immediate delivery, contrary to the original batch description. [Protocol Amendment A](experiment-protocol.md#amendment-a--scheduling-clarification-after-initial-outcome-inspection) | Original snapshot retained; correction made after initial outcomes were seen. Do not call the final rerun an independent preregistered replication. |
| A particular message caused useful progress | Unestablished causal claim | Proposed checkpoint/fork design in [protocol](experiment-protocol.md) | Current numbered-message withholding is a filter without full checkpoint restoration or semantic leakage control. |
| Live workers improve on a deterministic solver | Unestablished empirical claim | Requires a suitable task and controlled comparison | The tiny Terra pilot's exact evaluator took about 0.095 ms, versus about 26.2 seconds for the worker phase. The pilot supports integration, not an advantage over deterministic search. |
| A contemporary frontier-lab mathematical effort explains this architecture | Omitted claim | No such claim is required by this article | Do not infer another organization's internal architecture or proof status from conversation, a headline or a reconstructed diagram. |

The supplied UCF mirror of Smith's paper returned HTTP 403 during direct fetch.
The author's own hosted PDF above was available and verified. Publication dates
are taken from the papers, not search-engine crawl dates. Summaries are original
paraphrases; the repository does not reproduce the papers' text or figures.

For observed comparative outcomes, use the results report and preserved campaign
manifest. Update this register with exact artifact paths and code revisions only
after those measurements exist. Distinguish a successful test, a measured run,
an architectural intention and a general scientific conclusion.
