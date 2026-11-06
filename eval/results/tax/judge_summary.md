# TaxRAG answers (qwen2.5:7b): blind correctness judging (held-out test split)

79 answerable questions, 483 distinct answers graded by two independent LLM judges (opposite reading orders, configuration hidden), a third on each disagreement; the grade is the agreed one or the median of three. Agreement between the first two: 0.95, Cohen's κ 0.92.

Correct (all): correct 1, partial 0.5, incorrect or refused 0, over every answerable question. Fully correct (all): only `correct` counts. Wrong (all): share of questions answered incorrectly (lower is better).

| Configuration | Answered | Correct / partial / incorrect | Correct (all) | Fully correct (all) | Wrong (all) |
|---|---|---|---|---|---|
| `teammate-improved@gemini` | 66/79 | 35 / 11 / 20 | 0.513 | 0.443 | 0.253 |
| `R6x@gemini` | 65/79 | 35 / 10 / 20 | 0.506 | 0.443 | 0.253 |
| `R6d@gemini` | 57/79 | 27 / 13 / 17 | 0.424 | 0.342 | 0.215 |
| `teammate-improved@bge-m3` | 58/79 | 35 / 11 / 12 | 0.513 | 0.443 | 0.152 |
| `R5@budget` | 68/79 | 37 / 15 / 16 | 0.563 | 0.468 | 0.203 |
| `R6x` | 60/79 | 36 / 10 / 14 | 0.519 | 0.456 | 0.177 |
| `R5+expand` | 61/79 | 31 / 14 / 16 | 0.481 | 0.392 | 0.203 |
| `R6y@gemini` | 64/79 | 35 / 10 / 19 | 0.506 | 0.443 | 0.241 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0. For wrong (all), a negative difference favours A.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A higher / lower |
|---|---|---|---|---|---|---|
| `R6x@gemini` | `teammate-improved@gemini` | A* dependencies in place of his expansion, his deployed setup otherwise | correct (all) | -0.006 [-0.095, +0.089] | 0.854 | 11/11 |
| `R6x@gemini` | `teammate-improved@gemini` | A* dependencies in place of his expansion, his deployed setup otherwise | fully correct (all) | +0.000 [-0.101, +0.114] | 1.000 | 10/10 |
| `R6x@gemini` | `teammate-improved@gemini` | A* dependencies in place of his expansion, his deployed setup otherwise | wrong (all) | +0.000 [-0.076, +0.076] | 1.000 | 5/5 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | correct (all) | -0.006 [-0.076, +0.070] | 0.767 | 10/8 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | fully correct (all) | +0.000 [-0.089, +0.101] | 1.000 | 7/7 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | wrong (all) | -0.013 [-0.076, +0.051] | 1.000 | 3/4 |
| `R6d@gemini` | `teammate-improved@gemini` | A* evidence in place of his whole context, on his Gemini ranking | correct (all) | -0.089 [-0.203, +0.025] | 0.091 | 12/18 |
| `R6d@gemini` | `teammate-improved@gemini` | A* evidence in place of his whole context, on his Gemini ranking | fully correct (all) | -0.101 [-0.215, +0.013] | 0.088 | 7/15 |
| `R6d@gemini` | `teammate-improved@gemini` | A* evidence in place of his whole context, on his Gemini ranking | wrong (all) | -0.038 [-0.139, +0.051] | 0.439 | 6/9 |
| `R5@budget` | `teammate-improved@bge-m3` | Experiment 3 retrieval (R5) vs his `improved`, same local embedder | correct (all) | +0.051 [-0.051, +0.158] | 0.325 | 18/14 |
| `R5@budget` | `teammate-improved@bge-m3` | Experiment 3 retrieval (R5) vs his `improved`, same local embedder | fully correct (all) | +0.025 [-0.089, +0.152] | 0.670 | 12/10 |
| `R5@budget` | `teammate-improved@bge-m3` | Experiment 3 retrieval (R5) vs his `improved`, same local embedder | wrong (all) | +0.051 [-0.063, +0.152] | 0.346 | 11/7 |
| `R5+expand` | `teammate-improved@bge-m3` | R5 vs his `improved`, same local embedder and context layout (hits + his expansion) | correct (all) | -0.032 [-0.133, +0.076] | 0.555 | 13/16 |
| `R5+expand` | `teammate-improved@bge-m3` | R5 vs his `improved`, same local embedder and context layout (hits + his expansion) | fully correct (all) | -0.051 [-0.177, +0.076] | 0.414 | 10/14 |
| `R5+expand` | `teammate-improved@bge-m3` | R5 vs his `improved`, same local embedder and context layout (hits + his expansion) | wrong (all) | +0.051 [-0.025, +0.127] | 0.344 | 7/3 |
| `R5@budget` | `R5+expand` | his one-hop expansion removed, R5 hits | correct (all) | +0.082 [-0.013, +0.177] | 0.068 | 16/9 |
| `R5@budget` | `R5+expand` | his one-hop expansion removed, R5 hits | fully correct (all) | +0.076 [-0.025, +0.177] | 0.157 | 12/6 |
| `R5@budget` | `R5+expand` | his one-hop expansion removed, R5 hits | wrong (all) | +0.000 [-0.101, +0.089] | 1.000 | 7/7 |
| `R6x` | `R5+expand` | A* dependencies vs his expansion, after the R5 hits | correct (all) | +0.038 [-0.044, +0.127] | 0.443 | 12/7 |
| `R6x` | `R5+expand` | A* dependencies vs his expansion, after the R5 hits | fully correct (all) | +0.063 [-0.025, +0.165] | 0.197 | 10/5 |
| `R6x` | `R5+expand` | A* dependencies vs his expansion, after the R5 hits | wrong (all) | -0.025 [-0.114, +0.063] | 0.774 | 5/7 |
| `R5@budget` | `teammate-improved@gemini` | the local pipeline (no API key) vs his deployed Gemini retrieval | correct (all) | +0.051 [-0.057, +0.158] | 0.325 | 18/14 |
| `R5@budget` | `teammate-improved@gemini` | the local pipeline (no API key) vs his deployed Gemini retrieval | fully correct (all) | +0.025 [-0.101, +0.139] | 0.683 | 13/11 |
| `R5@budget` | `teammate-improved@gemini` | the local pipeline (no API key) vs his deployed Gemini retrieval | wrong (all) | -0.051 [-0.165, +0.051] | 0.371 | 8/12 |
| `teammate-improved@gemini` | `teammate-improved@bge-m3` | his `improved`: Gemini vs the local embedder | correct (all) | +0.000 [-0.101, +0.108] | 1.000 | 16/16 |
| `teammate-improved@gemini` | `teammate-improved@bge-m3` | his `improved`: Gemini vs the local embedder | fully correct (all) | +0.000 [-0.127, +0.127] | 1.000 | 14/14 |
| `teammate-improved@gemini` | `teammate-improved@bge-m3` | his `improved`: Gemini vs the local embedder | wrong (all) | +0.101 [-0.013, +0.215] | 0.074 | 14/6 |
