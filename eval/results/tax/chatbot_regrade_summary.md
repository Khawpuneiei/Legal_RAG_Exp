# Skeptical re-grade of the sample

88 distinct answers of the 25-question sample re-graded blind by two fresh judges (told that some systems are better than others, to list every claim and recompute every figure). Agreement 0.91, Cohen's κ 0.82; the lower grade where they differ.
Grades changed from the first round: 8 of 100 ({'claude-closed': 6, 'claude-rag': 1, 'qwen3-rag': 1}).

## The 25-question sample (every system)

| System | Answered | Correct / partial / incorrect | Correct (all) | Fully correct (all) | Wrong (all) |
|---|---|---|---|---|---|
| `claude-rag` | 25/25 | 21 / 3 / 1 | 0.900 | 0.840 | 0.040 |
| `claude-closed` | 25/25 | 7 / 11 / 7 | 0.500 | 0.280 | 0.280 |
| `qwen3-rag` | 23/25 | 13 / 8 / 2 | 0.680 | 0.520 | 0.080 |
| `iras-bot` | 15/25 | 12 / 2 / 1 | 0.520 | 0.480 | 0.040 |

Paired over these questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A higher / lower.

| A | B | Metric | Mean A − B [95% CI] | Wilcoxon p | A higher / lower |
|---|---|---|---|---|---|
| `claude-rag` | `claude-closed` | correct (all) | **+0.400 [+0.200, +0.580]** | 0.001 | 17/3 |
| `claude-rag` | `claude-closed` | wrong (all) | **-0.240 [-0.440, -0.040]** | 0.070 | 1/7 |
| `claude-rag` | `qwen3-rag` | correct (all) | **+0.220 [+0.100, +0.340]** | 0.006 | 11/1 |
| `claude-rag` | `qwen3-rag` | wrong (all) | -0.040 [-0.160, +0.080] | 1.000 | 1/2 |
| `claude-rag` | `iras-bot` | correct (all) | **+0.380 [+0.140, +0.600]** | 0.006 | 13/3 |
| `claude-rag` | `iras-bot` | wrong (all) | +0.000 [-0.120, +0.120] | 1.000 | 1/1 |

