# TaxRAG RQ1 and RQ2: protocol (written before any new answer was generated)

**Written:** 30 October 2026, before the skill was written and before any answer of the conditions below existed. Changes after this point are listed at the end with their reason.

**Questions.**
- **RQ1:** does a `SKILL.md` playbook make the teammate's tax answers more correct than his plain prompt?
- **RQ2:** does a harness beat his single LLM call? This includes **Deep Tax Research (DTR)**: a multi-step research mode in which R6y (A\* over dependency edges) is the "follow the references" step.

Both questions are the project plan's (Experiment 1 and Experiment 2), moved from drafting legal agreements to answering tax questions with his pipeline.

## Fixed setting (every condition)

- **Answer model:** qwen3:8b through Ollama 0.40.13, a local stand-in for his gpt-oss-120b.
  - One 16,384-token slot, so all 37 layers are on the GPU; flash attention; q8_0 KV cache.
  - Every condition's answers, including both baselines, are generated afresh with this setting. The earlier qwen3:8b round used 4 × 8,192 slots with 6 layers on the CPU, so its answers are not reused.
- **Answer call:** exactly his: `rag.generate.SYSTEM_PROMPT`, `build_prompt` over numbered sources, temperature 0, seed 0, his 2,000-token output cap with thinking on and counted in it. Then his `render_citations`: an answer with no valid `[n]` citation becomes his refusal sentence.
- **Helper calls** (skill routing, planning, gap check, agent steps): thinking off, JSON output, temperature 0, seed 0, at most 400 tokens. Thinking is off so that they are short and do not compete with the answer for the cap. His app would make them with gpt-oss-120b.
- **Retrieval:** his `improved` on his Gemini index (exact search), with his 2,500-token budget. R6y adds at most 450 tokens of A\* over dependency edges (λ = μ = 0, tuned on dev earlier). New search queries are embedded with his Gemini embedder on the free tier and cached.
- **Questions:**
  - Dev split (50: 40 answerable, 10 out of scope): writing the skill, pilots, and the single pre-registered choice below.
  - Test split (99: 79 answerable, 20 out of scope): every headline number. No test answer of a new condition is generated before the skill and every prompt are frozen.

## Conditions

| ID | Question | What differs from B0 |
|---|---|---|
| **B0** | baseline | his deployed context: `improved` hits plus his one-hop expansion; his prompt (= S0 = H0) |
| **B1** | baseline | R6y: `improved` hits plus A\* over dependency edges (450 tokens) |
| **S1** | RQ1 | the whole skill appended to his system prompt |
| **S2** | RQ1 | focused skill: SKILL.md plus at most 2 topic modules, picked by a routing call that sees the question and the module index; in the user message |
| **S3** | RQ1 | comprehensive skill: every skill file, in the user message |
| **S4** | RQ1 | a skill that qwen3:8b wrote for itself, in the user message |
| **V** | RQ2 | B0 plus a validation retry (below) |
| **DTR** | RQ2 | Deep Tax Research, fixed pipeline (below), at B1's token budget |
| **DTR+V** | RQ2 | DTR plus the validation retry |
| **DTRa** | RQ2 | Deep Tax Research as an agent (below), at B1's token budget |
| **DTRa+V** | RQ2 | DTRa plus the validation retry |
| **C** | both | the combination chosen on dev (rule below) |

The legal S1 to S4 place the skill the same way: S1 in the system prompt, S2 to S4 in the user prompt inside `<skill>` tags after "The following skill is loaded." The legal S5 and S0s (a smaller model) are not run on tax. Neither is H4, the multi-agent harness: it was the worst-but-one condition on legal, and it costs the most.

### Validation retry (V)

After his citation checker, the reply is checked for three problems:
- **V1:** an empty reply, or a reply that stopped at the 2,000-token cap (`done_reason` = length);
- **V2:** a reply that is not his exact refusal sentence but has no valid `[n]` citation;
- **V3:** citation numbers that are not among the sources.

On a problem, the same sources are sent again with a short note naming it. There are at most 2 retries, as in the legal H3 (`MAX_REFLECTION_ROUNDS = 2`). The model's own exact refusal is never retried. The last reply goes through his checker as usual. Unlike the legal H3, there is no rule override: on tax, his checker already owns the final decision, so V tests the feedback alone.

### Deep Tax Research, fixed pipeline (DTR)

1. **Plan** (helper call): up to 3 search queries for the provisions the question needs.
2. **Search:** his `improved` ranking (his 50 candidates) for the question and for each query. The lists are merged by reciprocal-rank fusion, with the question's list counted twice, then cut to his 2,500-token budget. The question's list alone gives exactly his hits, so with no queries DTR equals B1.
3. **Follow the references:** R6y from the merged hits, within 450 tokens.
4. **Gap check** (helper call): given the question and the numbered sources, up to 2 search queries for anything still missing, or none.
5. If there are gap queries, they are searched, merged with the earlier lists, and steps 2 and 3 are redone.
6. **Answer:** his answer call over the final sources.

The token budget is the same as B1's, so DTR can only change which evidence is chosen, not how much. There are 2 helper calls and 1 answer call.

### Deep Tax Research as an agent (DTRa)

The agent starts from the question's ranking, packed as above. At each step (helper call) it sees the question, the current numbered sources and its earlier steps, and picks one tool:
- `search(query)`: adds that query's ranking to the merge;
- `follow_references(sources)`: A\* from the chosen sources, within what is left of the 450-token allowance;
- `answer`: stops.

There are at most 5 steps, and the 5th must be `answer`. A repeated identical call is refused by the code. After the agent stops, any remaining allowance is filled by R6y from all hits. Then comes his answer call. This is the tax analogue of the legal H2: a ReAct loop with text-JSON tools.

### The skill

- **Author:** Claude agents.
- **Source material:**
  - his corpus (the Act chunks and the IRAS e-Tax guides in his repo);
  - error notes from the blind-judged dev answers of B0 in this round.
- **Kept away from the authors:** the test questions and every test answer. The orchestrator has seen the earlier test round's error types (listed in `docs/taxrag-results.md`) and does not pass them on.
- **Content rules:**
  - Procedural only: how to read and apply the sources, which conditions to check for each topic, and where to look (section and paragraph pointers are allowed).
  - No rates, thresholds, amounts, dates, caps or other tax facts; those must come from the cited sources.
  - It keeps his rules: `[n]` citations and the exact refusal sentence.
- **Layout:** `skills/tax-answering/`:
  - `SKILL.md`: at most 600 words;
  - one module per area of the held-out set: group relief, loss carry-back, start of business, renovation and deductions and capital allowances, and the general Act (at most 450 words each).
- **S4:** qwen3:8b writes its own `SKILL.md`, once and cached:
  - thinking on, temperature 0.7, seed 0, at most 6,000 tokens (the legal S4 used temperature 0.7, seed 0);
  - input: a task description with his rules and the five areas, and no corpus text.
- **Frozen:** the SHA-256 of every skill file is recorded below before any test answer of S1 to S4 or C.

### The pre-registered choice of C (on dev)

C combines the best skill with the best evidence step, judged on dev correct (all):
- **skill:** none, S1, S2, S3 or S4, whichever is highest. Within 0.01 of the highest, the shortest prompt wins.
- **evidence:** B0, B1, DTR or DTRa, whichever is highest. Within 0.01, the fewest calls wins.
- **validation retry:** included if V scores at least as high as B0 on dev.

The skill was written partly from dev errors, so dev favours the skill conditions. This is a bias in the choice of C, not in its test result.

## Judging

- **Rubric and procedure:** the same as the earlier rounds.
- **Blind:** each question's distinct answers from every condition are shown side by side, shuffled, with the configuration hidden.
- **Judges:** two judges read in opposite orders, and a third grades each disagreement (median of three). B0 and B1 are graded again in this round.
- **Order:** dev is judged first: the B0 and B1 answers for the skill authors, then every condition for the choice of C. Test is judged once, after all test answers exist.

## Analysis

**Primary measure:** correct (all) on the 79 answerable test questions. Correct = 1, partial = 0.5, incorrect or unanswered = 0. Differences are paired over questions, with a bootstrap 95% CI (2,000 resamples, seed 0) and a Wilcoxon p.

**Primary comparisons:**
1. RQ1: **S2 − B0**;
2. RQ2, the loop: **V − B0**;
3. RQ2, research: **DTR − B0**.

Holm-adjusted Wilcoxon p is reported for these three.

**Secondary comparisons:**
- S1, S3 and S4 − B0;
- S2 − S3;
- DTR − B1 (research beyond A\*);
- DTRa − DTR;
- DTR+V − DTR;
- DTRa+V − DTRa;
- C − B0.

**Also reported:** answered, gold cited (all), citation precision, out-of-scope refused, gold sections in the context, calls, tokens and seconds per question, and replies stopped at the cap.

**Reproducibility check:** B0 in this round against B0 in the earlier qwen3:8b round. Same retrieval and prompt; different server layout.

## RQ1 on legal agreements (the deferred Experiment 1 run)

The test-split run of `eval/exp12.py --exp 1` runs as designed: qwen2.5:7b, 3 seeds, 90 requests, the server at 4 × 8,192 slots as in Experiment 2. It is followed by `eval/generation_eval_graph.py` and `eval/judge.py`.

One bug in S2 is fixed before the run. An empty module name matched every file, and the 3-file cap followed index order instead of the model's order. The fix is disclosed; the dev pilot used the buggy version.

## Skill freeze (30 October 2026, 23:55 SGT, before any test answer of S1 to S4 or C)

```
bc878894771734c1ec6e1c96ce5d483d80c9a22c11edc5177642bbf5678f88c3  skills/tax-answering/SKILL.md
0e9fc53b6e770f7101fa66addd05bea0958d7197a8435cd8a73be7234db1e877  skills/tax-answering/modules/carry-back.md
553eccd7566c2e996c2b50497245adf731f0ca442042af4ee30a0270e22ac3a2  skills/tax-answering/modules/general-act.md
0dc05170d252f5f31b26b2786ae642ebd163abcf7b58efa7659642bb150794a7  skills/tax-answering/modules/group-relief.md
9ba42f7794d9a5ab5be9febb413f39b9a412eb52be7db1a612178c908d45b5c9  skills/tax-answering/modules/renovation-deductions-allowances.md
18108d73a3933dc00ada52ada2016e70ab0d0d996d71b50ddb0c821718e6f782  skills/tax-answering/modules/start-of-business.md
08a61d4f675b9db352b8e20ddb3e4bf030eaea9cd09d8ab1e3cae0ad40f6d201  skills/tax-answering-self/SKILL.md
```

**How the skill was written:**
- One Claude agent wrote error notes from the 40 blind-judged dev questions: B0 and B1, 70 distinct answers, κ 0.92.
- Six agents, one per file, wrote from those notes, the guides and the Act chunks.
- Two reviewers checked it: one for rule compliance, one for substance. Fixers applied their findings. The main fix: the model never sees the corpus's former-section field, so the skill must not refer to it.
- The skill is procedural and states no figures. In a few places it still says how a rule works, without figures; for example, which way a balancing adjustment goes.
- The S4 skill (234 words in the body) is qwen3:8b's own. It names wrong sections and asks for citations such as "[Section 15(1)]", which his citation checker does not accept. It is used as written.

## Changes after this protocol

- **C is defined:** the skill goes into the answer call only, not into the planning, gap or agent calls. Defined before any C answer.
- **Rerun as one job list:** the dev runs of V, DTR and DTRa were stopped part-way and restarted together with S1 to S4. Cached calls were reused, so nothing that was already answered changed.
- **Fixes from an independent code review (31 October 2026, before any test answer).** Four reviewers each checked one dimension, and every finding was verified by a skeptic. 10 were confirmed, 14 rejected. Fixed:
  1. **V:** a second retry after a second cap failure sent the identical prompt, which returned the same cached reply. Each retry's note now names the retry ("retry 1 of 2"), and the last one adds "reason in a few sentences at most".
  2. **DTRa `follow_references`:** A\* started from the chosen sources without knowing the other sources were already present. It spent the allowance re-adding them and could report "nothing to add". The other sources are now passed as present: they resolve dependencies at no cost (`ClauseGraph.astar(present=...)`; unchanged when empty).
  3. **DTR gap queries:** these are now de-duplicated against the plan's queries ignoring case, before the cap of 2, as in the kit for his repo.
  4. **Seconds per question:** now Ollama's own compute time, without time spent queueing behind another client.
  5. **Search queries:** new queries use his embedder's patient path, which retries server and connection errors, instead of the app's fail-fast path. Same model and vectors.
  6. **Reporting:** the Holm adjustment of the three primary comparisons, and model tokens per question, are now computed.
  7. **Dev choice of C:** judged in one fresh round with every condition side by side, as for test. `prep` refuses to relabel a round that already has verdicts.
  8. The skill's main file was renamed from `skill.md` to `SKILL.md`. The content and SHA-256 are unchanged.
- **Retrieval-only check on dev, and one control added (31 October 2026, before any test answer).** On the first 8 dev questions, DTR's sources held fewer gold sections. Over all 40 answerable dev questions (gold units in the sources):

  | Variant | Gold units | Tokens |
  |---|---|---|
  | B0 | 0.917 | 2,765 |
  | B1 | 0.917 | 2,758 |
  | DTR, plan only | 0.917 | 2,782 |
  | DTR as registered, plan + gap | 0.854 | 2,812 |
  | his hits kept, research only in the 450-token tail | 0.917 | 2,762 |
  | question counted as much as all sub-queries | 0.917 | 2,795 |
  | his hits plus 1,500 tokens of research | 0.929 | 4,254 |
  | his own ranking with a 4,000-token budget | 0.942 | 4,421 |

  - No same-budget variant beats B0, so **DTR is kept as registered**.
  - **B0w is added as a control:** his `improved` with a 4,000-token budget plus his expansion. It tests whether simply more of his own ranking does as well as research. Comparisons: B0w − B0 and DTR − B0w. B0w is not one of C's options.
- **The dev choice of C (31 October 2026, before any test answer was judged or read).** All 12 conditions were judged on dev in one fresh round: 331 distinct answers, side by side and shuffled, agreement 0.94, κ 0.87. Correct (all) on the 40 answerable dev questions:

  | Step | Options (dev correct, all) | Chosen |
  |---|---|---|
  | Skill | none 0.738, S1 0.787, **S2 0.800**, S3 0.725, S4 0.762 | S2 (no other within 0.01) |
  | Evidence | B0 0.738, **B1 0.762**, DTR 0.725, **DTRa 0.762** | B1 (tied with DTRa; 1.0 calls against 4.4) |
  | Validation retry | V 0.787 against B0 0.738 | included |

  **C = B1 evidence + S2 skill + V retry**, computed by `eval/tax_rq12.py choose` into `eval/results/tax/rq12_choice.json`. The test run of the 12 other conditions started 1 minute before this choice and was restarted with C added. No test answer was judged or read; the restart reused every cached call.

## Results

Judged on 1 November 2026: [`docs/taxrag-rq12-results.md`](taxrag-rq12-results.md).
