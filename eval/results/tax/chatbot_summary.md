# Claude in the tax RAG against existing tax chatbots: blind correctness judging

79 answerable held-out test questions, 243 distinct answers graded by two LLM judges (opposite reading orders, system hidden), a third on each disagreement. Agreement between the first two: 0.95, Cohen's κ 0.91.

Correct (all): correct 1, partial 0.5, incorrect or no answer 0, over every question. Wrong (all): share answered incorrectly (lower is better). A chatbot's "please rephrase" fallback or a decline counts as no answer.

## The 25-question sample (every system)

| System | Answered | Correct / partial / incorrect | Correct (all) | Fully correct (all) | Wrong (all) |
|---|---|---|---|---|---|
| `claude-rag` | 25/25 | 22 / 2 / 1 | 0.920 | 0.880 | 0.040 |
| `claude-closed` | 25/25 | 11 / 9 / 5 | 0.620 | 0.440 | 0.200 |
| `qwen3-rag` | 23/25 | 14 / 7 / 2 | 0.700 | 0.560 | 0.080 |
| `iras-bot` | 15/25 | 12 / 2 / 1 | 0.520 | 0.480 | 0.040 |

Paired over these questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A higher / lower.

| A | B | Metric | Mean A − B [95% CI] | Wilcoxon p | A higher / lower |
|---|---|---|---|---|---|
| `claude-rag` | `claude-closed` | correct (all) | **+0.300 [+0.100, +0.480]** | 0.010 | 14/2 |
| `claude-rag` | `claude-closed` | wrong (all) | -0.160 [-0.360, +0.000] | 0.219 | 1/5 |
| `claude-rag` | `qwen3-rag` | correct (all) | **+0.220 [+0.080, +0.360]** | 0.010 | 10/1 |
| `claude-rag` | `qwen3-rag` | wrong (all) | -0.040 [-0.160, +0.080] | 1.000 | 1/2 |
| `claude-rag` | `iras-bot` | correct (all) | **+0.400 [+0.180, +0.620]** | 0.005 | 13/2 |
| `claude-rag` | `iras-bot` | wrong (all) | +0.000 [-0.120, +0.120] | 1.000 | 1/1 |

## All 79 questions (the systems that answered all of them)

| System | Answered | Correct / partial / incorrect | Correct (all) | Fully correct (all) | Wrong (all) |
|---|---|---|---|---|---|
| `claude-rag` | 78/79 | 71 / 6 / 1 | 0.937 | 0.899 | 0.013 |
| `claude-closed` | 79/79 | 33 / 27 / 19 | 0.589 | 0.418 | 0.241 |
| `qwen3-rag` | 71/79 | 47 / 19 / 5 | 0.715 | 0.595 | 0.063 |

Paired over these questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A higher / lower.

| A | B | Metric | Mean A − B [95% CI] | Wilcoxon p | A higher / lower |
|---|---|---|---|---|---|
| `claude-rag` | `claude-closed` | correct (all) | **+0.348 [+0.247, +0.456]** | 0.000 | 45/6 |
| `claude-rag` | `claude-closed` | wrong (all) | **-0.228 [-0.329, -0.127]** | 0.000 | 1/19 |
| `claude-rag` | `qwen3-rag` | correct (all) | **+0.222 [+0.139, +0.304]** | 0.000 | 31/3 |
| `claude-rag` | `qwen3-rag` | wrong (all) | -0.051 [-0.114, +0.000] | 0.219 | 1/5 |

