# TaxRAG: do the Experiment 3 methods transfer to Singapore income tax? — results

**Run date:** 29–30 October 2026 · **Machine:** Windows 11 laptop, RTX 4060 (8 GB), 16 GB RAM · **Teammate's repo:** [Saiharshaa/SGtax-rag](https://github.com/Saiharshaa/SGtax-rag) at `ac04f49` · **Code:** `eval/tax_experiment.py`, `eval/tax_generation.py`, `eval/tax_judge.py`, `eval/tax_checks.py`, `src/tax/` · **Raw outputs:** `eval/results/tax/`

## Answer in one paragraph

**A\* graph expansion** is the one method with the same retrieval effect on tax as on legal agreements. As on legal agreements, the abstention gate is not needed, because the answer model abstains by itself (qwen2.5:7b on all 20 out-of-scope test questions, qwen3:8b on 19). With qwen2.5:7b, none of the four methods makes the answers more correct. With qwen3:8b only R6y (A\* in place of his expansion) was answered. It is level with his deployed context, and the projection says the gate would lower correctness.

- **A\* makes the evidence more self-contained.**
  - At the same 2,500-token budget, from his seeds, it resolves about twice as many cross-references, definitions and split provisions as his flat hits (12.8 vs 6.1) and leaves about a third as many unresolved (6.2 vs 17.7).
  - Against his flat hits, gold sections fall −0.049, not significant. That matches the legal result (definition coverage +0.64, clause recall −0.04 n.s.).
  - Against his one-hop expansion, A\* in place of the whole context does lose gold sections significantly: −0.070 inside the same budget, and −0.091 against the context his app sends.
- **R6y, the variant to integrate, keeps his hits and replaces only his one-hop expansion** with A\* over dependency edges. With the same tokens it resolves 0.706 of the hits' own dependencies against 0.499 for his expansion (+0.207 [+0.174, +0.242]), with the same gold recall.
  - An earlier variant, R6x, also followed embedding neighbours and was tuned on a different objective. It looked better on a share measure, but that measure's denominator grows with what the expansion adds. On the hits' own dependencies, R6x is worse than his expansion. An adversarial review caught this; see Method.
- **The cross-encoder reranker does not transfer.** It helped on all three legal datasets. On tax it gives a small, non-significant gain on the local embedder, and on his Gemini retrieval no variant beats his `improved`. On his own routed first stage it is significantly worse (−0.089 R@2,500, −0.129 MRR).
- **Contextual chunks** give a non-significant +0.03 R@2,500 here, against the largest gain on legal data.
- **The abstention gate** catches 75% of out-of-scope questions on his Gemini ranking. The answer model already refuses the out-of-scope test questions by itself: qwen2.5:7b all 20, qwen3:8b 19, with the 20th unanswered at the token cap. On answerable ones the gate suppresses 5 answers (−0.063 answered, significant). With qwen2.5:7b, 3 of those were wrong and 2 right; with qwen3:8b none was wrong.
- **With qwen2.5:7b, no configuration is significantly more or less correct than his `improved` retrieval.** This comes from blind judging of 483 distinct qwen2.5:7b answers (two judges, κ = 0.92). R6y vs his deployed context: −0.006 [−0.076, +0.070].
- **With a local reasoning model, qwen3:8b under his 2,000-token cap, R6y is also level with his deployed context.** It scores 0.753 correct (all) against 0.728: +0.025 [−0.038, +0.089], not significant. A fresh three-judge re-grade of the 20 questions where the two differ gives +0.006 [−0.057, +0.070]. His app's own model, gpt-oss-120b, was not run.
- **The answer model is the bottleneck.** With his Gemini retrieval, every gold section is in the context for 67 of 79 test questions. qwen2.5:7b gets only 30 of its 56 answers to them fully correct. Over all 79, on the same retrieved contexts, qwen3:8b raises his deployed setup's correct (all) from 0.513 to 0.728 (0.51 to 0.77 on those 67) and cuts wrong answers from 25% to 6%. That is a far larger change than any retrieval method made.
- **RQ1 and RQ2** (a skill, a validation retry and Deep Tax Research on top of his pipeline, qwen3:8b, 1 November 2026) are reported in [`docs/taxrag-rq12-results.md`](taxrag-rq12-results.md). Only the retry never lowered a score (+0.038, 4 better / 0 worse, n.s.). Deep Tax Research and the skill did not help.

"Significant" means the 95% paired bootstrap CI of the difference excludes zero (2,000 resamples, Wilcoxon p also reported). Every number below is in `eval/results/tax/`:
- `summary.md`: retrieval, graph and gate;
- `generation_summary.md`: answers;
- `judge_summary.md`: correctness;
- the `_qwen3-8b` versions of the last two: the qwen3:8b run;
- `checks_qwen3-8b.md`: the token cap, the questions with every gold section in the context, the gate projection for both models, and the re-grade.

## Verdict per method

| Method | Legal agreements (Experiment 3) | Tax, held-out test (79 answerable questions) | Transfers? | For his repo |
|---|---|---|---|---|
| Cross-encoder reranker (R4) | nDCG@10 +0.072, significant | Local embedder: R@2,500 +0.036, MRR −0.015 (n.s.). On his Gemini retrieval no variant of `bge-reranker-v2-m3` beats his `improved`. On top of his own routed first stage it loses −0.089 R@2,500 and −0.129 MRR (significant). The fused variant on his hybrid + boost first stage is neutral on ranking against that first stage | **No** | Don't add. The CPU MiniLM version in `integrations/bc3415-tax-rag/` is significantly worse on MRR and is withdrawn |
| Contextual chunks (R5) | Recall@5 +0.130; LegalBench-RAG recall 0.35 → 0.63 | R@2,500 +0.032 (n.s.) on the local embedder. On Gemini: not run (needs re-embedding every chunk with his key) | **Not shown** | Don't add yet. Re-embedding costs his Gemini quota |
| A\* graph expansion (R6d) | Definition coverage +0.639, clause recall −0.038 (n.s.) | Same budget, his seeds: dependencies resolved 6.1 → 12.8, unresolved 17.7 → 6.2, flat hits' dependencies +0.176 (all significant); gold sections −0.049 vs his flat hits (n.s.), but −0.070 vs his one-hop expansion inside the budget (significant). R5 seeds: unresolved −15.5, gold −0.032 (n.s.). The 7B model then answers fewer questions: −0.20 vs flat R5 (significant), −0.11 vs his deployed context on Gemini (n.s.). Judged correctness, measured only on Gemini: −0.089 [−0.203, +0.025] vs his deployed context (n.s.) | **Yes, for evidence completeness**; no answer gain | Not as a replacement for his context |
| A\* over dependency edges in place of his one-hop expansion (R6y, new) | – | Hits' own dependencies resolved 0.706 vs 0.499 (+0.207 [+0.174, +0.242]); gold sections 0.926 vs 0.918 (n.s.); tokens 2,766 vs 2,753. The whole context ends with 6.1 more unresolved references (26.0 vs 19.9): its additions bring their own. Correct (all) with qwen2.5:7b −0.006 [−0.076, +0.070], answered −0.025 (n.s.); with the reasoning model qwen3:8b +0.025 [−0.038, +0.089] (n.s.) | Yes, for evidence completeness; no answer gain | **Opt-in config** (`improved_astar`), no embeddings needed. Keep `improved` the default until it is tested with gpt-oss-120b. With the local reasoning model it shows no significant loss, though a loss of up to about 4 points is not ruled out |
| A\* with embedding neighbours in place of his expansion (R6x, new) | – | Hits' own dependencies −0.059 [−0.096, −0.025] vs his expansion (worse); gold +0.004 (n.s.). Correct (all) with qwen2.5:7b −0.006 [−0.095, +0.089] (n.s.); not run with qwen3:8b | No | Superseded by R6y |
| Calibrated abstention gate | Not needed: the drafter declined all 10 unsupported asks by itself | Gemini (τ = 0.6825): catches 15 of 20 out-of-scope and refuses 6% of answerable questions. The model already refuses 20/20 out-of-scope test questions (qwen2.5:7b; qwen3:8b 19/20, the 20th unanswered at the cap). On answerable ones the gate suppresses 5 answers (answered −0.063, significant). With qwen2.5:7b, 3 had been judged wrong and 2 right (projected wrong 0.253 → 0.215, correct 0.513 → 0.487). With qwen3:8b, 2 correct and 3 partial, none wrong (projected wrong unchanged at 0.063, correct 0.728 → 0.684, −0.044 [−0.089, −0.013]). Projections from the ungated answers, not a gate run | **Same finding**: the model abstains on its own | Optional: saves 20% of calls. With qwen2.5:7b it removes a few wrong answers at the cost of a few right ones; with qwen3:8b it removes none and costs some right ones |

## Results

### Reproduction of his numbers

All eight rows of his published table (Recall@5, MRR, Recall @ 2,500 tokens on his 28 questions) reproduce **exactly** through his own code, his chunks and his Gemini vectors (`summary.md`, first table). His claim also holds on our held-out questions: `improved` beats `baseline` on his Gemini index by +0.139 R@2,500 [+0.061, +0.222] and +0.124 MRR@10.

### Flat retrieval (held-out test split, 79 answerable questions, 2,500-token budget)

| Condition | Recall @ 2,500 | MRR@10 | Recall@5 | nDCG@10 |
|---|---|---|---|---|
| his `baseline` (naive chunks, Gemini dense) | 0.736 | 0.725 | 0.736 | 0.702 |
| **his `improved` (Gemini), as deployed** | **0.876** | **0.849** | **0.821** | **0.800** |
| R4 on his Gemini hybrid + boost | 0.749 | 0.687 | 0.671 | 0.653 |
| R4f (reranker fused with first stage) on Gemini | 0.808 | 0.769 | 0.719 | 0.730 |
| R4 on his `improved` first stage (Gemini) | 0.787 | 0.720 | 0.696 | 0.682 |
| his `improved` on the local embedder (BGE-M3) | 0.700 | 0.657 | 0.627 | 0.615 |
| R4 hybrid + boost + reranker (BGE-M3) | 0.736 | 0.679 | 0.646 | 0.644 |
| R5 = R4 + contextual chunks (BGE-M3) | 0.768 | 0.677 | 0.690 | 0.659 |

- **The reranker hurts on his deployed retrieval.** `bge-reranker-v2-m3` reorders his Gemini top 50 worse than his own fusion and routing. R4 on his `improved` first stage loses −0.089 R@2,500 [−0.160, −0.023] and −0.129 MRR. R4 on his hybrid + boost first stage, which has no routing, loses more against his `improved` (−0.127 / −0.162). Fusing the reranker's rank with that first stage (R4f) roughly halves this to −0.068 / −0.080, both significant. Most of the remaining MRR gap is the missing routing: hybrid + boost alone trails `improved` by −0.070 of the −0.080. On R@2,500, routing accounts for only −0.025 (n.s.) of the −0.068; the rest is R4f's own loss against its first stage. Against its own first stage, R4f is neutral on ranking (MRR −0.010, nDCG@10 +0.006, n.s.) and loses −0.042 R@2,500 [−0.089, −0.004]. So no reranker variant beats his retrieval, and on his own routed first stage it is clearly worse.
- **On the local embedder the reranker and contexts help a little.** R5 vs his `improved` on BGE-M3: +0.068 R@2,500 [−0.004, +0.146], p = 0.074. Not significant.
- **The CPU variants are worse.** The int8 MiniLM reranker shipped earlier in `integrations/bc3415-tax-rag/` (D3i) keeps R@2,500 (−0.011, n.s.) but loses −0.167 MRR@10 [−0.240, −0.091] on his deployed retrieval. Recommendation: do not merge it.

### Graph expansion (2,500-token budget; A\* tuned on the dev split)

Four measures of how self-contained the evidence is, all on the graph's dependency edges:

- **flat hits' dependencies resolved**: the share of the flat budgeted hits' own cross-references, definitions and split pieces that the evidence resolves. It has a fixed denominator per question, so it compares strategies fairly.
- **resolved** and **unresolved**: counts of dependencies in the whole evidence.
- **all dependencies** and **definitions resolved**: shares over whatever the evidence contains, overall and for definitions only. These were the only dependency measures in the first version of this write-up. Their denominator grows with every chunk an expansion adds, so an expansion that brings in chunks with references of their own scores lower on them, even when it resolves more of what the hits need. His expansion's 0.083 on definitions is an example: the same hits alone score 0.396.

| Condition | Gold sections in evidence | Flat hits' dependencies resolved | Definitions resolved (share) | All dependencies (share) | Resolved / unresolved (count) | Tokens |
|---|---|---|---|---|---|---|
| R5, flat | 0.768 | 0.201 | 0.381 | 0.201 | 7.3 / 22.2 | 2,349 |
| R6d: A\* from the R5 seeds | 0.736 | 0.317 | 0.663 | 0.608 | 14.1 / 6.7 | 2,481 |
| his `improved` (Gemini), flat | 0.876 | 0.248 | 0.396 | 0.248 | 6.1 / 17.7 | 2,337 |
| R6d@gemini: A\* from his seeds | 0.827 | 0.424 | 0.671 | 0.638 | 12.8 / 6.2 | 2,478 |
| **his app's context: hits + one-hop expansion** | 0.918 | 0.499 | 0.083 | 0.361 | 10.3 / 19.9 | 2,753 |
| R6x@gemini: his hits + A\* (dependencies and embedding neighbours) | 0.922 | 0.439 | 0.395 | 0.429 | 11.7 / 16.4 | 2,765 |
| **R6y@gemini: his hits + A\* over dependency edges only** | 0.926 | **0.706** | 0.452 | 0.453 | 20.8 / 26.0 | 2,766 |

- **A\* in place of the flat context, same budget (R6d), improves every measure.** From his seeds it resolves about twice as many dependencies (12.8 vs 6.1) and leaves about a third as many unresolved (6.2 vs 17.7, −11.5 [−14.4, −8.9]). It also resolves more of the flat hits' own dependencies (+0.176 [+0.120, +0.233]). From R5 seeds: +0.116 and −15.5 unresolved.
  - Against the flat hits, gold sections fall −0.049 and −0.032, not significant. Against his one-hop expansion inside the same budget, A\* from his seeds loses −0.070 [−0.131, −0.015] (significant; from R5 seeds −0.046, n.s.). Against the context his app sends (hits + expansion, 2,753 tokens) the loss is −0.091 [−0.150, −0.034].
  - The first version reported +0.39 / +0.41 on the share measure. That figure overstates the effect, but the direction holds on every measure.
  - A\* drops some lower-ranked hits to make room for dependencies. From his seeds, on the flat hits' own dependencies it is level with BFS (−0.032 [−0.095, +0.031], n.s.) and below his one-hop expansion inside the same budget (R6-onehop@gemini, 0.473 in `summary.md`; −0.049 [−0.098, −0.001]). It leaves far fewer dependencies unresolved than either (−11.9 and −11.1).
- **R6x does not beat his expansion on the hits' own dependencies.** It is worse there (−0.059 [−0.096, −0.025]).
  - Its +0.068 on the share measure came from what each method adds to the denominator: his expansion adds the first chunk of up to 3 cited sections, and those chunks bring references of their own.
  - On the whole-evidence counts R6x does better: +1.4 resolved, −3.5 unresolved, both significant. But those counts also depend on what the added chunks bring.
  - On the 79 answerable test questions, 342 of the 522 chunks R6x@gemini adds (66%) resolve no dependency at all. They are embedding neighbours and guide paragraphs reached from the hits.
- **R6y, the fix: A\* over dependency edges only.** With the same hits and tokens, it resolves +0.207 [+0.174, +0.242] more of the hits' own dependencies than his expansion (better on 67 questions, worse on 1). It also resolves twice as many dependencies in all (20.8 vs 10.3). Gold sections are unchanged (+0.008, n.s.).
  - The cost: the whole context ends with 6.1 more unresolved dependencies (26.0 vs 19.9, +6.1 [+3.9, +8.2]). Its additions bring about 11 more unresolved references of their own (17.1 vs 6.0 per question), partly offset by about 5 fewer of the hits' dependencies left unresolved (8.8 vs 13.9). The 450-token allowance cannot cover those as well. Against R6x: +9.6 unresolved.
  - From the R5 hits, R6y vs his expansion: +0.163 on the hits' dependencies.
  - Tuned on dev, its query-similarity weight and heuristic weight both came out 0 for both seeds. R6y is therefore a cheapest-first search over dependency edges that needs no embeddings.
  - R6y differs from R6x in two ways. It drops the seed-only edges, and it was tuned on a different objective: gold plus the flat hits' dependencies, against R6x's gold plus share measures. That moved λ, μ from 0.5, 2 to 0, 0. Both changes matter. On dev, the hits' own dependencies resolved are:
    - his expansion: 0.519;
    - R6x: 0.404;
    - dependency edges only, at R6x's λ and μ: 0.534;
    - R6y: 0.707.
- **Caveat on these metrics:** dependencies are measured on the same regex cross-reference graph that A\* searches, so every dependency measure favours the graph methods by construction. Gold sections are independent of the graph. The legal definition-coverage metric has the same share form as *all dependencies*.

### Abstention gate

Refuse when the best dense similarity (or reranker score) is below τ, with τ chosen by Youden's J on the dev split. On his Gemini ranking (τ = 0.6825), the gate refuses 15 of 20 out-of-scope test questions and 6% of answerable ones; on R5 (τ = 0.262), 16 of 20 and 22%. In the answer runs, qwen2.5:7b refused all 20 out-of-scope test questions in every configuration (and 9 or 10 of 10 on dev), so on out-of-scope test questions the gate changes nothing but the number of model calls: 5 of 20 instead of 20 of 20. Over all test questions that is 79 of 99 calls, counting 5 gated answerable questions. On answerable questions it suppresses 5 answers on his deployed retrieval (answered −0.063 [−0.127, −0.013]). The gate configurations were not judged, but those 5 answers were judged without the gate.
- **qwen2.5:7b:** 3 were wrong and 2 right. Gating them would lower the wrongly-answered share from 0.253 to 0.215 and correct (all) from 0.513 to 0.487.
- **qwen3:8b:** the gate depends only on retrieval, so it would gate the same 5 questions. That model's answers to them were judged 2 correct and 3 partial, none wrong. Gating them would leave the wrongly-answered share at 0.063 and lower correct (all) from 0.728 to 0.684.

These are projections from the ungated answers; no gate configuration was run.
- **qwen2.5:7b:** the projected changes are not significant: wrongly answered −0.038 [−0.089, +0.000], correct (all) −0.025 [−0.063, +0.000].
- **qwen3:8b:** all 5 answers lose credit, so the projected drop in correct (all), −0.044 [−0.089, −0.013], has a bootstrap CI that excludes zero. Its Wilcoxon p is 0.062, as only 5 questions move.

On dev, with qwen2.5:7b (the only model run on dev), his `improved`, R6x@gemini and R6y@gemini each answered the same out-of-scope question (h084). The gate would have refused it in all three, since its top similarity was 0.675, below τ.

### Answers (qwen2.5:7b with his prompt, numbered sources, citation rewriting and refusal rule)

Every configuration uses the same local model, so differences come from retrieval and evidence selection only. Gold cited (all) is the share of a question's gold sections the answer cites, with a refusal counting as 0. Correct (all) is from the blind judging: correct = 1, partial = 0.5, incorrect or refused = 0.

| Configuration | Answered (of 79) | Gold cited (all) | Correct / partial / incorrect | Correct (all) | Answered wrongly |
|---|---|---|---|---|---|
| his `improved` (Gemini), as deployed | 66 | 0.610 | 35 / 11 / 20 | 0.513 | 0.253 |
| R6y@gemini (his hits + A\* over dependency edges) | 64 | 0.624 | 35 / 10 / 19 | 0.506 | 0.241 |
| R6x@gemini | 65 | 0.624 | 35 / 10 / 20 | 0.506 | 0.253 |
| R6d@gemini | 57 | 0.519 | 27 / 13 / 17 | 0.424 | 0.215 |
| his `improved` (BGE-M3) | 58 | 0.500 | 35 / 11 / 12 | 0.513 | 0.152 |
| R5, flat | 68 | 0.603 | 37 / 15 / 16 | **0.563** | 0.203 |
| R5 + his expansion | 61 | 0.580 | 31 / 14 / 16 | 0.481 | 0.203 |
| R6x (R5 hits + A\*, with neighbours) | 60 | 0.576 | 36 / 10 / 14 | 0.519 | 0.177 |

- **R6y@gemini and R6x@gemini vs his deployed retrieval: no significant effect on these answers in either direction.**
  - R6y: gold cited (all) +0.015 [−0.051, +0.078], answered −0.025, correct (all) −0.006 [−0.076, +0.070], wrongly answered −0.013. On dev: gold cited (all) −0.037, answered +0.025 (both n.s.); one out-of-scope dev question was answered, as with his `improved`.
  - R6x: gold cited (all) +0.015, correct (all) −0.006 [−0.095, +0.089]. On dev: gold cited (all) −0.050 (n.s.). Dev answers had not been generated before, but dev retrieval had set both variants' parameters.
  - Losses of up to about 8 (R6y) or 10 (R6x) points of correctness are not ruled out.
- **R5 vs his `improved` on the same local embedder: no significant answer difference once the context layout matches.**
  - Flat R5 against his `improved`, which also sends his one-hop expansion: gold cited (all) +0.103 [+0.019, +0.196] and answered +0.127, both significant. Judged correctness +0.051 [−0.051, +0.158], not significant.
  - Most of the answered and correctness gaps come from leaving out his expansion: answered +0.089 of +0.127, and correct (all) +0.082 against a same-layout difference that is negative. The gold-cited gap mostly remains with the same layout (+0.080 of +0.103) but is no longer significant. With the same layout (R5 hits plus his expansion vs his `improved`): gold cited (all) +0.080 [−0.006, +0.169], answered +0.038, correct (all) −0.032 [−0.133, +0.076]. None is significant.
  - Removing his expansion from the R5 context on its own: answered +0.089 [+0.025, +0.165] (significant), correct (all) +0.082 [−0.013, +0.177] (n.s.). The extra sections make the 7B model refuse more often.
- **R6d makes the model refuse more on R5.** In place of flat R5 at the same budget, A\*'s evidence costs −0.203 answered [−0.304, −0.126], significant. In place of his whole context on his Gemini ranking, the drop is −0.114 [−0.228, +0.000], not significant (dev: −0.125, n.s.). A\* spends budget on definitions and earlier pieces of split provisions, and the 7B model then more often decides the sources do not answer the question.
- **The answer model is the bottleneck.** With his Gemini retrieval, every gold section is in the context for 67 of 79 questions. The model still refuses 11 of them. Of the 56 answers it gives, 30 are fully correct, 9 partial and 17 (30%) wrong; correct (all) over the 67 is 0.51.
  - Typical errors are in applying the rule rather than finding it: multiplying indirect shareholdings for the 75% group test, time-apportioning a loss, and reading which items an IRAS table allows.
  - With these errors and 79 questions, retrieval changes of the size measured here are too small to show up as significant differences in correctness.
  - His app uses Groq `gpt-oss-120b`, with Gemini Flash as the fallback; these runs test neither. The next section uses a local reasoning model instead.
- **Judging reliability.** 483 distinct answers were graded. The first 424 were shown side by side per question, about five answers each. R6y's 59 new answers came later, in separate batches where each was shown alone, graded with the same rubric and two-judge procedure. Its other 5 answers matched answers already graded and kept their grades. Judges grading an answer in isolation may grade differently from judges comparing answers, so R6y's grades are not fully comparable. The two judges agreed on 95% of them (Cohen's κ 0.92); the 23 disagreements went to a third judge (median grade). All judges were Claude agents, which may share biases, and none of them is a tax professional.

### Answers with a reasoning model (qwen3:8b under his 2,000-token cap)

His app answers with `gpt-oss-120b`, a reasoning model. Its output cap of 2,000 tokens includes the reasoning (`rag/llm.py`, `MAX_ANSWER_TOKENS`). Neither that model nor his Gemini fallback could be run at scale:
- the Gemini key is on the free tier, 20 requests a day; 16 answers were generated before it ran out;
- no Groq key was available.

As a local stand-in, qwen3:8b, a reasoning model, ran through Ollama at temperature 0, which is also his app's temperature. It answered for R6y@gemini and his deployed `improved` with the same prompt, citation checker and 2,000-token cap, covering the test split and his 28 questions. That is 254 answers, which took 4.2 hours on the laptop. gpt-oss-20b, the smaller model in his model's own family, was not tried: it is a 14 GB model, against the laptop's 8 GB GPU and 16 GB RAM.

| Configuration | Answered (of 79) | Gold cited (all) | Citation precision | Correct / partial / incorrect | Correct (all) | Fully correct (all) | Answered wrongly |
|---|---|---|---|---|---|---|---|
| his `improved` (Gemini), as deployed | 71 | 0.764 | 0.553 | 49 / 17 / 5 | 0.728 | 0.620 | 0.063 |
| R6y@gemini (his hits + A\* over dependency edges) | 72 | 0.776 | 0.613 | 53 / 13 / 6 | 0.753 | 0.671 | 0.076 |

- **R6y vs his deployed context: no significant difference, with R6y slightly ahead.**
  - Correct (all) +0.025 [−0.038, +0.089] (Wilcoxon p = 0.44), higher on 12 questions and lower on 8.
  - Fully correct (all) +0.051 [−0.051, +0.152]; answered wrongly +0.013 [−0.038, +0.063]; gold cited (all) +0.013 [−0.049, +0.068].
  - On his 28 questions: gold cited (all) −0.013 [−0.160, +0.127], answered 23 vs 24 of 25 (n.s.).
  - A loss of more than about 4 points of correctness is outside the CI, or about 6 points in either check below. With qwen2.5:7b the bound was 8.
- **The result holds under two checks.**
  - *Re-grade.* A fresh panel of three blind judges re-graded the 20 questions where the two configurations' correct (all) scores differ. One graded in file order, one first worked out the answer from the sources as an examiner would, and one first compared the two answers.
    - The three agreed with each other on 35 of 36 answers, and their median matched the original grade on 31.
    - With the panel's grades, the difference is +0.006 [−0.057, +0.070]: higher on 10 questions, lower on 8.
    - Re-grading only the questions that differ can remove grading noise from them but cannot find new differences elsewhere, so it leans towards zero.
  - *Without the cap failures.* Leaving out the 8 questions where either configuration got no text back at the cap (next point) gives +0.007 [−0.056, +0.070] over the remaining 71. Also leaving out h082, where his `improved` reply was cut off at the cap (graded incorrect, as was R6y's), gives +0.007 [−0.057, +0.071] over 70.
- **The token cap costs answers, and so does his citation checker.**
  - 16 of the 250 distinct model calls reached the 2,000-token cap.
    - 13 of them spent it all on reasoning and returned no text. His `generate.py` counts that as a refusal.
    - The other 3 were cut off partway through the answer. Two of these cite a source, so they went out truncated: his `improved` on test question h082 and on his q13. The third, R6y on an out-of-scope question, had no citation yet and became a refusal.
  - On the answerable test questions, empty replies account for 7 of his `improved`'s 8 unanswered questions and 4 of R6y's 7; 3 of these questions failed in both. His 28 questions lost 2 R6y answers this way.
  - The model itself declined only 1 answerable test question, for `improved`. R6y's other 3 unanswered questions got full answers that named sections in the text instead of citing source numbers, so his checker replaced them with the refusal.
  - On the out-of-scope test questions the model wrote the refusal itself on 19 of 20 in both configurations. The 20th (h145) also ended as a refusal, but only through the cap: `improved` returned no text, and R6y was cut off a few words into an uncited answer.
  - His app has the same cap for gpt-oss-120b. How often that model reaches it at medium effort is untested.
- **A stronger answer model matters far more than any retrieval change.**
  - On the same contexts, qwen3:8b raises his deployed setup's correct (all) from 0.513 (qwen2.5:7b) to 0.728, and cuts the answered-wrongly share from 0.253 to 0.063.
  - On the 67 questions with every gold section in the context, qwen3:8b gives 43 fully correct, 17 partial, 4 wrong and 3 unanswered (correct (all) 0.77). qwen2.5:7b gave 30 / 9 / 17 / 11 (0.51).
  - Paired over the 79 questions, the gain is +0.215 [+0.095, +0.335] (higher on 29, lower on 12).
  - The two models were judged in separate rounds with the same rubric and procedure, but with about five answers per question shown together for qwen2.5:7b and two for qwen3:8b. No answer was graded in both rounds, so a shift in leniency between the rounds is not measured, and the comparison across models is approximate. The gap is still much larger than the disagreement between judges within either round.
- **Judging.**
  - 142 distinct answers to 75 questions were graded; both configurations left the other 4 unanswered.
  - Both configurations' answers to a question were shown side by side, as in the first round.
  - The two judges agreed on 140 (Cohen's κ 0.97), and a third graded the 2 disagreements.

## What this means for his repo

1. **Keep his retrieval as it is.** His `improved` on Gemini is the best ranking we measured. No reranker; the earlier `integrations/bc3415-tax-rag/rag/rerank.py` is withdrawn.
2. **Offer R6y as an opt-in configuration** (`improved_astar`: A\* over dependency edges in place of `Corpus.expand`). It resolves more of what the hits depend on, for the same tokens and gold recall: the hits' own dependencies resolved rise from 0.50 to 0.71. Its additions also bring references of their own, so the context ends with about 6 more unresolved ones (26.0 vs 19.9). It needs no embeddings, and the graph is built from the chunks in 0.2 s. Judged correctness does not change significantly, either with qwen2.5:7b or with the reasoning model qwen3:8b (+0.025 [−0.038, +0.089]), a local stand-in for his gpt-oss-120b. Keep `improved` as the default until R6y is tested with gpt-oss-120b itself: `eval/tax_generation.py --model groq --configs teammate-improved@gemini R6y@gemini` runs that test once a Groq key is in his `.env`, next to the `GEMINI_API_KEY` that the `@gemini` retrieval needs. The kit is in `integrations/bc3415-tax-rag/` (a patch for his repo at `ac04f49`).
3. **The abstention gate is optional.** It saves 20% of model calls. On the 5 answerable questions it suppressed, it removed 3 wrong answers and 2 right ones with qwen2.5:7b. With qwen3:8b none of the 5 was wrong (2 correct, 3 partial), so there it would only cost correctness: 0.728 → 0.684, −0.044 [−0.089, −0.013]. That is a projection from the ungated answers, not a gate run. Add it if calls cost money. Whether it removes more wrong answers than right ones depends on the answer model, and that is untested with gpt-oss-120b. His `generate.py` already treats an uncited answer as a refusal.
4. **Add our held-out questions to his evaluation.** They are 119 answerable questions against his 25, about five times as many, with types and areas labelled. On his Gemini index they rank his eight configurations in the same order as his own set on Recall @ 2,500, his headline metric (ties aside); on MRR@10 and Recall@5 the order changes more. On Recall@5 his `baseline` drops from 2nd to 5th, and on MRR@10 `structured_bm25_boost` moves from last to first of the three BM25 configurations. The file needs converting first:
   - cut each row down to his seven `Question` fields;
   - write dev and test as separate files, because his format has no `split` field;
   - merge the evidence quotes back from `.cache/tax/heldout_evidence.jsonl`. They are blank in our public file, and without them his evidence test passes without checking anything.
5. **Watch the answer-token cap.** With qwen3:8b, his 2,000-token cap, which counts reasoning tokens, was reached on 16 of 250 calls (6%).
   - 13 of these returned no text. His `generate.py` turns them into refusals, and they were most of the unanswered test questions.
   - The other 3 were cut off partway through the answer: 2 went out truncated, and 1 became a refusal.
   - It is untested whether gpt-oss-120b reaches the cap. Logging when a reply stops at the cap (Groq's `finish_reason`) would show it, and would catch truncated answers too.
   - A higher `MAX_ANSWER_TOKENS` may recover some of these answers, but no run tested it. The reasoning was not saved, so it is unknown whether the capped calls were long but finishing, or repeating. qwen3:8b also ran at temperature 0, and Qwen advises against greedy decoding in its thinking mode because the reasoning can repeat without end.

## Reproducing

```
python scripts/build_tax_questions.py <audited.json>   # needs the audited drafts (IRAS quotes, not distributed); writes the
                                                       # frozen data/tax/questions_heldout.jsonl and .cache/tax/heldout_evidence.jsonl
python -m src.tax.contextual                           # R5's chunk contexts (qwen2.5:7b through Ollama), cached
python eval/tax_experiment.py all                      # rank, graph, gate, report -> eval/results/tax/
python eval/tax_generation.py                          # answers, held-out test + his 28
python eval/tax_generation.py --split dev --configs teammate-improved@gemini R6d@gemini R6x@gemini R6y@gemini R5+expand R6x
python eval/tax_judge.py prep 6 teammate-improved@gemini R6x@gemini R6d@gemini teammate-improved@bge-m3 R5@budget R6x R5+expand
python eval/tax_judge.py add 2 R6y@gemini              # R6y's answers, graded after the others without relabelling them
python eval/tax_judge.py score                         # after the judges' verdicts are in .cache/tax/judge/verdicts.json
python eval/tax_generation.py --model qwen3:8b --configs teammate-improved@gemini R6y@gemini   # reasoning stand-in, -> *_qwen3-8b
python eval/tax_judge.py prep 4 teammate-improved@gemini R6y@gemini --suffix _qwen3-8b
python eval/tax_judge.py score --suffix _qwen3-8b      # verdicts in .cache/tax/judge_qwen3-8b/verdicts.json
python eval/tax_checks.py regrade-prep                 # the questions where R6y and his `improved` differ, for a fresh panel
python eval/tax_checks.py report                       # cap, gold in context, gate projection, re-grade -> checks_qwen3-8b.md
```

Needs his repo in `TAX_RAG_DIR` (default `../bc3415-tax-rag`) with his built index, and `GEMINI_API_KEY` in his `.env` or ours (both git-ignored) for the `@gemini` rows: only the query embeddings are requested, his chunk vectors are read from his index. The IRAS evidence quotes, chunk contexts, answer texts and judge batches stay in `.cache/tax/`, outside the repo. Retrieval, graph, gate and answers run from a clean checkout. The judging step also needs `.cache/tax/heldout_evidence.jsonl`, so it cannot be rerun without the private drafts.

## Method

### Question and protocol

Do the Experiment 3 methods (cross-encoder reranker, contextual chunks, A\* graph expansion, calibrated abstention) improve retrieval and answers on the teammate's Singapore income-tax RAG as they did on legal agreements? Every method runs on his corpus, chunks, token counter, budget and scoring, through his code (`rag.retrieve`, `rag.generate`), so the comparison with his configurations is exact. All tuning (A\* λ, μ and seed count; R6x's and R6y's allowance, λ and μ; the gate's τ) uses the dev split, and no parameter was set from the test split. The test runs were repeated when exact search replaced Chroma. Two configurations, R6x and R6y, were added after earlier test results; both are listed below.

**Changes after the first test run, disclosed:**

- **R6x was added after the first test answers.** Those answers showed that A\* in place of his whole context made the model refuse more. R6x keeps his hits and only replaces his expansion. Its allowance (450 tokens) is his expansion's mean on dev, and λ, μ were tuned on dev retrieval. Its answers were then also run on dev. No earlier choice had used dev answers, though dev retrieval had set R6x's allowance, λ and μ.
- **R6y and the fixed-denominator measures were added after an adversarial review of this write-up.** The review found that R6x's advantage on the share measure came from the denominator. On the hits' own dependencies, R6x was worse than his expansion on test. R6y (dependency edges only) was then:
  1. prototyped on dev;
  2. tuned on dev for gold recall plus the flat hits' dependencies (a grid of λ × μ);
  3. scored on test once. Its qwen2.5:7b answers were run on the same protocol and graded with the same rubric and two-judge procedure, but in later batches where each new answer was shown alone. Its qwen3:8b answers were graded side by side with his `improved`'s.

  The R6d and R6x tunings did not change: the rerun reproduced their parameters exactly.
- **Exact search replaced Chroma.** Chroma's HNSW index returned different neighbours across process starts for 3 held-out questions. All `@gemini` rows now use exact cosine search over his stored vectors, in chunk order. A second full run from a fresh process gave byte-identical rankings, graph rows and tunings. His published table still reproduces exactly, and the conclusions did not change.
  - His app itself still uses HNSW. Its hit lists differ from exact search on 12–13 of the 177 questions, varying between process starts. None of those differences changes a gold section in the hits, in any split. So the exact-search numbers also hold for his app.
- **Blind correctness judging was added** after the citation metrics, because they cannot tell a right answer from a wrong one that cites the right section.

### Data

| Set | Questions | Built by | Use |
|---|---|---|---|
| His `eval/questions.jsonl` | 28 (25 answerable, 3 out of scope) | him | reproduction; reported, not used for decisions |
| Held-out (`data/tax/questions_heldout.jsonl`) | 149: dev 50 (40 + 10 out of scope), **test 99 (79 + 20 out of scope)**. Test types: 59 natural, 16 naming a section, 4 using a pre-2020 section number | us | dev: all tuning; test: frozen, headline numbers |

The held-out questions were written by five agents, one per area: group relief; loss carry-back; start of business; renovation, deductions and capital allowances; and the general Act. Five other agents audited each question's evidence quote, gold completeness, wording leakage and out-of-scope claims. Then deterministic checks ran (`scripts/build_tax_questions.py`):

- each evidence quote appears verbatim in a gold chunk (his test rule);
- each gold unit exists in his corpus;
- the question type matches his section detector;
- no run of 7 words is copied from a gold chunk;
- no near duplicate of another question or of his 28.

150 were written and 149 kept. Gold units are (Act section) or (guide, paragraph), his scoring unit.

### Conditions

| ID | First stage | Extras |
|---|---|---|
| his configs (`naive_*`, `structured_*`, `improved`) | his code, on BGE-M3 (`@bge-m3`) or his Gemini vectors (`@gemini`) | as published |
| R4 | his hybrid + section boost (structured chunks, BM25 + dense, RRF k = 60) | `BAAI/bge-reranker-v2-m3` over the top 50 |
| R4f | as R4 | reranker rank fused with the first-stage rank (RRF) |
| R4-routed, R4-bm25, R4e | his routed first stage / BM25 only / Qwen3-Embedding-0.6B | reranker |
| R5, R5f | as R4, R4f | contextual chunks: 1–2 sentences per chunk by qwen2.5:7b, from the chunk's section (Act) or the guide's headings and neighbouring paragraphs |
| D1, D2, D1i, D3, D3i | CPU variants | MiniLM-L6 reranker (int8 ONNX in D1i, D3i: the earlier integration) |
| R6a, R6c, R6d | top seeds of R5 or of his `improved` | BFS depth 2 / A\* admissible / A\* tuned, within the 2,500-token budget |
| R6x | R5's hits (R6x) or his `improved` hits (R6x@gemini) within the budget | A\* adds chunks within 450 extra tokens, in place of his `Corpus.expand`: dependencies, plus embedding neighbours and guide paragraphs from the hits |
| R6y | as R6x | the same search over dependency edges only (λ = μ = 0 after tuning, so cheapest first) |
| +gate | any | refuse before generation when the top score is below τ |

The graph (`src/tax/graph.py`) has one node per chunk. Its dependency edges:

- **REFERS_TO**: "subsection (4)", "subsection (1) of section 37B", "paragraph 6.1", and his own section cross-references;
- **DEFINED_IN**: "In this section …" and "For the purposes of subsection (7) …";
- **CONTINUES**: the pieces of a split provision.

It also has two kinds of seed-only edges: guide paragraphs that cite an Act section, and the 3 nearest neighbours by embedding (R6y does not follow them). The A\* search is the Experiment 3 one (`src/retrieval/graph.py`). It now has two options: seeds pinned in the evidence (R6x, R6y) and no seed-only edges (R6y). With both changes it still gives identical results on the legal benchmark (448 of 448 rows).

### Metrics

- **Retrieval:** Recall @ 2,500 tokens (his headline metric), MRR@10, Recall@5 and nDCG@10 over his gold units.
- **Graph:** gold units in the evidence, and four dependency measures:
  - the share of the flat budgeted hits' own dependencies resolved in the evidence (fixed denominator);
  - counts of resolved and unresolved dependencies in the evidence;
  - the share of the evidence's dependencies resolved in it, overall and by type (cross-reference, definition, continuation). Its denominator depends on what the evidence contains.
- **Answers** (qwen2.5:7b through Ollama, and qwen3:8b for R6y@gemini vs his `improved`; his prompt and citation checker):
  - answered;
  - his citation precision;
  - gold cited and gold cited (all);
  - out-of-scope refused;
  - model calls.
- **Correctness:** blind grading (correct / partial / incorrect) of each distinct answer. Judges saw the question, the evidence quote and the gold sections. Each section was cut at 9,000 characters: for Act sections the evidence chunk comes first, then document order; guide paragraphs are in document order. 34 of the 76 questions judged for qwen2.5:7b (31 of 75 for qwen3:8b) had at least one gold section cut short. Two independent judges read in opposite orders, without seeing which configuration wrote an answer; a third judge graded each disagreement. Answers identical across configurations were graded once.

### Limitations

- **The held-out questions were written by us** (LLM agents, audited by LLM agents and code checks), not by tax professionals or real users. His 28 questions point the same way, but they are too few to decide anything.
- **The answer models are local.** qwen2.5:7b answered every configuration, and the 8B reasoning model qwen3:8b answered R6y and his `improved`. His app uses `gpt-oss-120b`, which was not run. With qwen3:8b, R6y is not significantly different from his deployed context (correct (all) +0.025 [−0.038, +0.089]). A loss of up to about 4 points of correctness (about 6 in the two checks) is not ruled out. A much larger model may still use A\*'s extra definitions better, or not need them.
- **The dependency measures favour the graph methods**, because they are counted on the graph A\* searches. The share measure also grows or shrinks with what an expansion adds; the first version of this write-up relied on it and drew the wrong conclusion about R6x.
- **R6y was designed after test results were seen** (R6x's), although its parameters were tuned on dev only and it was scored on test once.
- **The judges are LLMs** from one model family; agreement is high (κ 0.92 in the qwen2.5:7b round, 0.97 in the qwen3:8b round), but shared bias is possible. They saw long gold sections cut at 9,000 characters, so an answer relying on the omitted part may have been under-graded.
- **Contextual chunks were not run on Gemini**, because that needs every chunk re-embedded with his key.
- **Sample sizes are small:** 79 answerable test questions. With qwen2.5:7b, the 95% CIs on correct (all) span about ±0.07 (R6y@gemini vs his deployed context) to ±0.11. With qwen3:8b, the same R6y comparison is about ±0.06, and qwen3:8b vs qwen2.5:7b on his `improved` about ±0.12. Correctness differences of up to about 0.06–0.12, depending on the comparison (such as R6d@gemini's −0.089 with qwen2.5:7b), are within noise.
