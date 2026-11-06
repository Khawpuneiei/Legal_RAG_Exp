# TaxRAG answers (qwen3:8b, local, reasoning): blind correctness judging (held-out test split)

79 answerable questions, 142 distinct answers graded by two independent LLM judges (opposite reading orders, configuration hidden), a third on each disagreement; the grade is the agreed one or the median of three. Agreement between the first two: 0.99, Cohen's κ 0.97.

Correct (all): correct 1, partial 0.5, incorrect or refused 0, over every answerable question. Fully correct (all): only `correct` counts. Wrong (all): share of questions answered incorrectly (lower is better).

| Configuration | Answered | Correct / partial / incorrect | Correct (all) | Fully correct (all) | Wrong (all) |
|---|---|---|---|---|---|
| `teammate-improved@gemini` | 71/79 | 49 / 17 / 5 | 0.728 | 0.620 | 0.063 |
| `R6y@gemini` | 72/79 | 53 / 13 / 6 | 0.753 | 0.671 | 0.076 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0. For wrong (all), a negative difference favours A.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A higher / lower |
|---|---|---|---|---|---|---|
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | correct (all) | +0.025 [-0.038, +0.089] | 0.437 | 12/8 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | fully correct (all) | +0.051 [-0.051, +0.152] | 0.317 | 10/6 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | wrong (all) | +0.013 [-0.038, +0.063] | 1.000 | 3/2 |
