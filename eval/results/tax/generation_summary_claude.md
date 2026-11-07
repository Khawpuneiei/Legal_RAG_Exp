# TaxRAG answers (claude-opus-5-5, the teammate's prompt and citation checker)

Citation precision: share of an answer's citations that point at a gold unit (his metric). Gold cited: share of the question's gold units the answer cites, over answered answerable questions. Gold cited (all): the same over every answerable question, a refusal counting as 0, so a configuration cannot score higher by answering less.

## Teammate's 28 questions

| Configuration | Answerable answered | Out-of-scope refused | Citation precision | Gold cited | Gold cited (all) | Model calls | Source tokens |
|---|---|---|---|---|---|---|---|
| `teammate-improved@gemini` | 25/25 | 3/3 | 0.359 | 0.827 | 0.827 | 28/28 | 2886 |
| `R6y@gemini` | 25/25 | 3/3 | 0.393 | 0.833 | 0.833 | 28/28 | 2776 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A better / worse |
|---|---|---|---|---|---|---|
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | gold cited (all) | +0.007 [-0.067, +0.080] | 1.000 | 2/2 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | answered | +0.000 [+0.000, +0.000] | – | 0/0 |

## Held-out test split

| Configuration | Answerable answered | Out-of-scope refused | Citation precision | Gold cited | Gold cited (all) | Model calls | Source tokens |
|---|---|---|---|---|---|---|---|
| `teammate-improved@gemini` | 78/79 | 20/20 | 0.472 | 0.889 | 0.878 | 99/99 | 2750 |
| `R6y@gemini` | 79/79 | 20/20 | 0.511 | 0.907 | 0.907 | 99/99 | 2768 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A better / worse |
|---|---|---|---|---|---|---|
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | gold cited (all) | +0.030 [-0.000, +0.065] | 0.156 | 5/1 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | answered | +0.013 [+0.000, +0.038] | – | 1/0 |

