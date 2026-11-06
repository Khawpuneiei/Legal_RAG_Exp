# TaxRAG answers (qwen3:8b, local, reasoning; RQ1 and RQ2): blind correctness judging (held-out test split)

79 answerable questions, 741 distinct answers graded by two independent LLM judges (opposite reading orders, configuration hidden), a third on each disagreement; the grade is the agreed one or the median of three. Agreement between the first two: 0.94, Cohen's κ 0.88.

Correct (all): correct 1, partial 0.5, incorrect or refused 0, over every answerable question. Fully correct (all): only `correct` counts. Wrong (all): share of questions answered incorrectly (lower is better).

| Configuration | Answered | Correct / partial / incorrect | Correct (all) | Fully correct (all) | Wrong (all) |
|---|---|---|---|---|---|
| `B0` | 71/79 | 52 / 14 / 5 | 0.747 | 0.658 | 0.063 |
| `B1` | 70/79 | 56 / 9 / 5 | 0.766 | 0.709 | 0.063 |
| `B0w` | 69/79 | 50 / 14 / 5 | 0.722 | 0.633 | 0.063 |
| `S1` | 76/79 | 50 / 12 / 14 | 0.709 | 0.633 | 0.177 |
| `S2` | 75/79 | 49 / 16 / 10 | 0.722 | 0.620 | 0.127 |
| `S3` | 76/79 | 41 / 21 / 14 | 0.652 | 0.519 | 0.177 |
| `S4` | 71/79 | 43 / 21 / 7 | 0.677 | 0.544 | 0.089 |
| `V` | 77/79 | 54 / 16 / 7 | 0.785 | 0.684 | 0.089 |
| `DTR` | 71/79 | 49 / 16 / 6 | 0.722 | 0.620 | 0.076 |
| `DTR+V` | 77/79 | 50 / 18 / 9 | 0.747 | 0.633 | 0.114 |
| `DTRa` | 70/79 | 51 / 17 / 2 | 0.753 | 0.646 | 0.025 |
| `DTRa+V` | 77/79 | 56 / 18 / 3 | 0.823 | 0.709 | 0.038 |
| `C` | 79/79 | 54 / 14 / 11 | 0.772 | 0.684 | 0.139 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0. For wrong (all), a negative difference favours A.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A higher / lower |
|---|---|---|---|---|---|---|
| `S2` | `B0` | RQ1: focused skill vs his prompt | correct (all) | -0.025 [-0.108, +0.057] | 0.622 | 9/14 |
| `S2` | `B0` | RQ1: focused skill vs his prompt | fully correct (all) | -0.038 [-0.152, +0.076] | 0.513 | 9/12 |
| `S2` | `B0` | RQ1: focused skill vs his prompt | wrong (all) | +0.063 [+0.000, +0.127] | 0.125 | 6/1 |
| `S1` | `B0` | RQ1: whole skill in the system prompt vs his prompt | correct (all) | -0.038 [-0.127, +0.051] | 0.442 | 10/15 |
| `S1` | `B0` | RQ1: whole skill in the system prompt vs his prompt | fully correct (all) | -0.025 [-0.152, +0.089] | 0.670 | 10/12 |
| `S1` | `B0` | RQ1: whole skill in the system prompt vs his prompt | wrong (all) | **+0.114 [+0.038, +0.190]** | 0.012 | 10/1 |
| `S3` | `B0` | RQ1: comprehensive skill vs his prompt | correct (all) | **-0.095 [-0.184, -0.013]** | 0.041 | 8/18 |
| `S3` | `B0` | RQ1: comprehensive skill vs his prompt | fully correct (all) | **-0.139 [-0.253, -0.038]** | 0.016 | 5/16 |
| `S3` | `B0` | RQ1: comprehensive skill vs his prompt | wrong (all) | **+0.114 [+0.025, +0.203]** | 0.020 | 12/3 |
| `S4` | `B0` | RQ1: skill written by the model itself vs his prompt | correct (all) | -0.070 [-0.146, +0.006] | 0.102 | 8/17 |
| `S4` | `B0` | RQ1: skill written by the model itself vs his prompt | fully correct (all) | -0.114 [-0.228, +0.000] | 0.050 | 6/15 |
| `S4` | `B0` | RQ1: skill written by the model itself vs his prompt | wrong (all) | +0.025 [-0.038, +0.089] | 0.727 | 5/3 |
| `S2` | `S3` | RQ1: focused vs comprehensive skill | correct (all) | +0.070 [-0.025, +0.165] | 0.155 | 19/12 |
| `S2` | `S3` | RQ1: focused vs comprehensive skill | fully correct (all) | +0.101 [-0.013, +0.228] | 0.117 | 17/9 |
| `S2` | `S3` | RQ1: focused vs comprehensive skill | wrong (all) | -0.051 [-0.139, +0.038] | 0.285 | 5/9 |
| `V` | `B0` | RQ2: validation retry vs his single call | correct (all) | **+0.038 [+0.006, +0.082]** | 0.125 | 4/0 |
| `V` | `B0` | RQ2: validation retry vs his single call | fully correct (all) | +0.025 [+0.000, +0.063] | 0.500 | 2/0 |
| `V` | `B0` | RQ2: validation retry vs his single call | wrong (all) | +0.025 [+0.000, +0.063] | 0.500 | 2/0 |
| `DTR` | `B0` | RQ2: Deep Tax Research vs his deployed context | correct (all) | -0.025 [-0.120, +0.070] | 0.630 | 13/16 |
| `DTR` | `B0` | RQ2: Deep Tax Research vs his deployed context | fully correct (all) | -0.038 [-0.165, +0.089] | 0.564 | 12/15 |
| `DTR` | `B0` | RQ2: Deep Tax Research vs his deployed context | wrong (all) | +0.013 [-0.051, +0.089] | 1.000 | 5/4 |
| `DTR` | `B1` | RQ2: Deep Tax Research vs R6y alone | correct (all) | -0.044 [-0.127, +0.032] | 0.266 | 8/13 |
| `DTR` | `B1` | RQ2: Deep Tax Research vs R6y alone | fully correct (all) | -0.089 [-0.203, +0.013] | 0.108 | 6/13 |
| `DTR` | `B1` | RQ2: Deep Tax Research vs R6y alone | wrong (all) | +0.013 [-0.063, +0.089] | 1.000 | 5/4 |
| `B1` | `B0` | R6y vs his deployed context (this round) | correct (all) | +0.019 [-0.063, +0.108] | 0.704 | 13/10 |
| `B1` | `B0` | R6y vs his deployed context (this round) | fully correct (all) | +0.051 [-0.063, +0.177] | 0.394 | 13/9 |
| `B1` | `B0` | R6y vs his deployed context (this round) | wrong (all) | +0.000 [-0.063, +0.063] | 1.000 | 3/3 |
| `B0w` | `B0` | control: his retrieval with 4,000 tokens instead of 2,500 | correct (all) | -0.025 [-0.127, +0.076] | 0.602 | 14/16 |
| `B0w` | `B0` | control: his retrieval with 4,000 tokens instead of 2,500 | fully correct (all) | -0.025 [-0.152, +0.101] | 0.695 | 12/14 |
| `B0w` | `B0` | control: his retrieval with 4,000 tokens instead of 2,500 | wrong (all) | +0.000 [-0.063, +0.063] | 1.000 | 3/3 |
| `DTR` | `B0w` | Deep Tax Research vs simply more of his own ranking | correct (all) | +0.000 [-0.101, +0.101] | 0.907 | 14/16 |
| `DTR` | `B0w` | Deep Tax Research vs simply more of his own ranking | fully correct (all) | -0.013 [-0.139, +0.114] | 0.847 | 13/14 |
| `DTR` | `B0w` | Deep Tax Research vs simply more of his own ranking | wrong (all) | +0.013 [-0.051, +0.076] | 1.000 | 4/3 |
| `DTRa` | `DTR` | RQ2: research agent vs fixed research pipeline | correct (all) | +0.032 [-0.051, +0.114] | 0.434 | 14/11 |
| `DTRa` | `DTR` | RQ2: research agent vs fixed research pipeline | fully correct (all) | +0.025 [-0.089, +0.152] | 0.683 | 13/11 |
| `DTRa` | `DTR` | RQ2: research agent vs fixed research pipeline | wrong (all) | -0.051 [-0.114, +0.000] | 0.219 | 1/5 |
| `DTR+V` | `DTR` | RQ2: validation retry on Deep Tax Research | correct (all) | +0.025 [+0.000, +0.063] | 0.250 | 3/0 |
| `DTR+V` | `DTR` | RQ2: validation retry on Deep Tax Research | fully correct (all) | +0.013 [+0.000, +0.038] | – | 1/0 |
| `DTR+V` | `DTR` | RQ2: validation retry on Deep Tax Research | wrong (all) | +0.038 [+0.000, +0.089] | 0.250 | 3/0 |
| `DTRa+V` | `DTRa` | RQ2: validation retry on the research agent | correct (all) | **+0.070 [+0.019, +0.133]** | 0.031 | 6/0 |
| `DTRa+V` | `DTRa` | RQ2: validation retry on the research agent | fully correct (all) | **+0.063 [+0.013, +0.127]** | 0.062 | 5/0 |
| `DTRa+V` | `DTRa` | RQ2: validation retry on the research agent | wrong (all) | +0.013 [+0.000, +0.038] | – | 1/0 |
| `C` | `B0` | the combination chosen on dev vs his deployed setup | correct (all) | +0.025 [-0.051, +0.108] | 0.495 | 11/9 |
| `C` | `B0` | the combination chosen on dev vs his deployed setup | fully correct (all) | +0.025 [-0.076, +0.139] | 0.637 | 10/8 |
| `C` | `B0` | the combination chosen on dev vs his deployed setup | wrong (all) | +0.076 [+0.000, +0.152] | 0.109 | 8/2 |

Primary comparisons (protocol): correct (all), Wilcoxon p and its Holm adjustment over the three.

| A | B | Mean A − B [95% CI] | Wilcoxon p | Holm p |
|---|---|---|---|---|
| `S2` | `B0` | -0.025 [-0.108, +0.057] | 0.622 | 1.000 |
| `V` | `B0` | **+0.038 [+0.006, +0.082]** | 0.125 | 0.375 |
| `DTR` | `B0` | -0.025 [-0.120, +0.070] | 0.630 | 1.000 |
