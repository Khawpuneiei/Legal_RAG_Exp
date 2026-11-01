# TaxRAG answers (qwen3:8b, the teammate's prompt and citation checker)

Citation precision: share of an answer's citations that point at a gold unit (his metric). Gold cited: share of the question's gold units the answer cites, over answered answerable questions. Gold cited (all): the same over every answerable question, a refusal counting as 0, so a configuration cannot score higher by answering less.

## Teammate's 28 questions

| Configuration | Answerable answered | Out-of-scope refused | Citation precision | Gold cited | Gold cited (all) | Model calls | Source tokens |
|---|---|---|---|---|---|---|---|
| `teammate-improved@gemini` | 24/25 | 3/3 | 0.427 | 0.736 | 0.707 | 28/28 | 2886 |
| `R6y@gemini` | 23/25 | 3/3 | 0.462 | 0.754 | 0.693 | 28/28 | 2776 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A better / worse |
|---|---|---|---|---|---|---|
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | gold cited (all) | -0.013 [-0.160, +0.127] | 0.977 | 4/5 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | answered | -0.040 [-0.200, +0.080] | 1.000 | 1/2 |

## Held-out test split

| Configuration | Answerable answered | Out-of-scope refused | Citation precision | Gold cited | Gold cited (all) | Model calls | Source tokens |
|---|---|---|---|---|---|---|---|
| `teammate-improved@gemini` | 71/79 | 20/20 | 0.553 | 0.850 | 0.764 | 99/99 | 2750 |
| `R6y@gemini` | 72/79 | 20/20 | 0.613 | 0.852 | 0.776 | 99/99 | 2768 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A better / worse |
|---|---|---|---|---|---|---|
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | gold cited (all) | +0.013 [-0.049, +0.068] | 0.485 | 8/6 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | answered | +0.013 [-0.051, +0.076] | 1.000 | 4/3 |

