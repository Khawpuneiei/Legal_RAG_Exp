# Claude in the tax RAG against existing tax chatbots: blind correctness judging

79 answerable held-out test questions, 155 distinct answers graded by two LLM judges (opposite reading orders, system hidden), a third on each disagreement. Agreement between the first two: 0.97, Cohen's κ 0.81.

Correct (all): correct 1, partial 0.5, incorrect or no answer 0, over every question. Wrong (all): share answered incorrectly (lower is better). A chatbot's "please rephrase" fallback or a decline counts as no answer.

## The 25-question sample (every system)

| System | Answered | Correct / partial / incorrect | Correct (all) | Fully correct (all) | Wrong (all) |
|---|---|---|---|---|---|
| `claude-dts` | 25/25 | 22 / 1 / 2 | 0.900 | 0.880 | 0.080 |
| `claude-rag` | 25/25 | 22 / 2 / 1 | 0.920 | 0.880 | 0.040 |

Paired over these questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A higher / lower.

| A | B | Metric | Mean A − B [95% CI] | Wilcoxon p | A higher / lower |
|---|---|---|---|---|---|
| `claude-dts` | `claude-rag` | correct (all) | -0.020 [-0.060, +0.000] | – | 0/1 |
| `claude-dts` | `claude-rag` | wrong (all) | +0.040 [+0.000, +0.120] | – | 1/0 |

## All 79 questions (the systems that answered all of them)

| System | Answered | Correct / partial / incorrect | Correct (all) | Fully correct (all) | Wrong (all) |
|---|---|---|---|---|---|
| `claude-dts` | 79/79 | 73 / 4 / 2 | 0.949 | 0.924 | 0.025 |
| `claude-rag` | 78/79 | 72 / 5 / 1 | 0.943 | 0.911 | 0.013 |

Paired over these questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A higher / lower.

| A | B | Metric | Mean A − B [95% CI] | Wilcoxon p | A higher / lower |
|---|---|---|---|---|---|
| `claude-dts` | `claude-rag` | correct (all) | +0.006 [-0.019, +0.038] | 1.000 | 1/1 |
| `claude-dts` | `claude-rag` | wrong (all) | +0.013 [+0.000, +0.038] | – | 1/0 |

