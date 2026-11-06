# TaxRAG answers (qwen3:8b): checks

Paired over the held-out test split's answerable questions: mean A − B [95% bootstrap CI]. A = `R6y@gemini`, B = `teammate-improved@gemini` unless stated. Correct (all): correct 1, partial 0.5, incorrect or unanswered 0.

- As judged (eval/results/tax/judge_summary_qwen3-8b.md): correct (all) +0.025 [-0.038, +0.089] (Wilcoxon p 0.437; higher / lower 12/8, n = 79)

## The 2,000-token cap

250 distinct model calls for 254 answers: where both configurations got the same sources (h014, h016, h025, q03), one call answered both. 16 calls reached the cap, 13 of them with no text (the reasoning used it all) and 3 cut off partway through the answer. The table counts answers, so a shared call counts once per configuration.

Unanswered questions by cause: no text at the cap, cut off at the cap, the model's own refusal sentence, or an answer his checker refused because it cites no source by number. The last column lists the unanswered questions that were not declined.

| Question set | Configuration | Unanswered | Cap, no text | Cap, cut off | Declined | Answer without a valid citation | Unanswered, not declined |
|---|---|---|---|---|---|---|---|
| test, answerable | `teammate-improved@gemini` | 8 | 7 | 0 | 1 | 0 | h014, h021, h035, h047, h048, h091, h097 |
| test, answerable | `R6y@gemini` | 7 | 4 | 0 | 0 | 3 | h003, h014, h048, h050, h097, h110, h143 |
| test, out of scope | `teammate-improved@gemini` | 20 | 1 | 0 | 19 | 0 | h145 |
| test, out of scope | `R6y@gemini` | 20 | 0 | 1 | 19 | 0 | h145 |
| his 28, answerable | `teammate-improved@gemini` | 1 | 0 | 0 | 1 | 0 |  |
| his 28, answerable | `R6y@gemini` | 2 | 2 | 0 | 0 | 0 | q02, q05 |
| his 28, out of scope | `teammate-improved@gemini` | 3 | 0 | 0 | 3 | 0 |  |
| his 28, out of scope | `R6y@gemini` | 3 | 0 | 0 | 3 | 0 |  |

Cut off at the cap but kept as answers (they cite a source): heldout h082 `teammate-improved@gemini`, reference q13 `teammate-improved@gemini`.

## Without the cap failures

- Leaving out the 8 test questions where either configuration got no text back (h003, h014, h021, h035, h047, h048, h091, h097): correct (all) +0.007 [-0.056, +0.070] (Wilcoxon p 0.827; higher / lower 10/8, n = 71)
- Also leaving out the cut-off replies (h082): correct (all) +0.007 [-0.057, +0.071] (Wilcoxon p 0.827; higher / lower 10/8, n = 70)

## Every gold section in his deployed context

67 test questions; his `improved` answers.

| Answer model | Correct | Partial | Incorrect | Unanswered | Correct (all) |
|---|---|---|---|---|---|
| qwen2.5:7b | 30 | 9 | 17 | 11 | 0.515 |
| qwen3:8b | 43 | 17 | 4 | 3 | 0.769 |

- qwen3:8b vs qwen2.5:7b, his `improved`, all answerable test questions (judged in separate rounds): correct (all) **+0.215 [+0.095, +0.335]** (Wilcoxon p 0.000; higher / lower 29/12, n = 79)

## The abstention gate, projected

The gate depends only on retrieval; on his deployed context it refuses 5 answerable test questions (h065, h108, h110, h129, h134). Projected from the ungated answers: those questions counted as unanswered (A = gated, B = `teammate-improved@gemini`).

- qwen2.5:7b: their grades incorrect, incorrect, incorrect, correct, correct; correct (all) -0.025 [-0.063, +0.000] (Wilcoxon p 0.500; higher / lower 0/2, n = 79); wrongly answered -0.038 [-0.089, +0.000] (Wilcoxon p 0.250; higher / lower 0/3, n = 79)
- qwen3:8b: their grades correct, partial, partial, correct, partial; correct (all) **-0.044 [-0.089, -0.013]** (Wilcoxon p 0.062; higher / lower 0/5, n = 79); wrongly answered +0.000 [+0.000, +0.000] (Wilcoxon p –; higher / lower 0/0, n = 79)

## Fresh re-grade of the questions where the two differ in correct (all)

20 questions, 36 graded answers, 36 graded by all three lenses.

- The three lenses agree on 35 of 36; their median equals the original grade on 31.
- With the panel's median grade on these questions: correct (all) +0.006 [-0.057, +0.070] (Wilcoxon p 0.870; higher / lower 10/8, n = 79)

