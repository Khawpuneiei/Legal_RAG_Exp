# TaxRAG answers (qwen3:8b, the teammate's prompt and citation checker)

Citation precision: share of an answer's citations that point at a gold unit (his metric). Gold cited: share of the question's gold units the answer cites, over answered answerable questions. Gold cited (all): the same over every answerable question, a refusal counting as 0, so a configuration cannot score higher by answering less.

## Held-out dev split (run after the first test run, to check the R6x variant on unseen answers)

| Configuration | Answerable answered | Out-of-scope refused | Citation precision | Gold cited | Gold cited (all) | Model calls | Source tokens |
|---|---|---|---|---|---|---|---|
| `teammate-improved@gemini` | 35/40 | 7/10 | 0.575 | 0.905 | 0.792 | 50/50 | 2760 |
| `R6y@gemini` | 35/40 | 7/10 | 0.561 | 0.848 | 0.742 | 50/50 | 2760 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A better / worse |
|---|---|---|---|---|---|---|
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | gold cited (all) | -0.050 [-0.150, +0.050] | 0.625 | 1/3 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | answered | +0.000 [-0.100, +0.100] | 1.000 | 2/2 |

