# TaxRAG answers (qwen3:8b, local, reasoning; RQ1 and RQ2): blind correctness judging (held-out dev split)

40 answerable questions, 331 distinct answers graded by two independent LLM judges (opposite reading orders, configuration hidden), a third on each disagreement; the grade is the agreed one or the median of three. Agreement between the first two: 0.94, Cohen's κ 0.87.

Correct (all): correct 1, partial 0.5, incorrect or refused 0, over every answerable question. Fully correct (all): only `correct` counts. Wrong (all): share of questions answered incorrectly (lower is better).

| Configuration | Answered | Correct / partial / incorrect | Correct (all) | Fully correct (all) | Wrong (all) |
|---|---|---|---|---|---|
| `B0` | 35/40 | 27 / 5 / 3 | 0.738 | 0.675 | 0.075 |
| `B1` | 35/40 | 28 / 5 / 2 | 0.762 | 0.700 | 0.050 |
| `B0w` | 34/40 | 26 / 7 / 1 | 0.738 | 0.650 | 0.025 |
| `S1` | 38/40 | 28 / 7 / 3 | 0.787 | 0.700 | 0.075 |
| `S2` | 37/40 | 29 / 6 / 2 | 0.800 | 0.725 | 0.050 |
| `S3` | 36/40 | 24 / 10 / 2 | 0.725 | 0.600 | 0.050 |
| `S4` | 37/40 | 25 / 11 / 1 | 0.762 | 0.625 | 0.025 |
| `V` | 38/40 | 28 / 7 / 3 | 0.787 | 0.700 | 0.075 |
| `DTR` | 38/40 | 25 / 8 / 5 | 0.725 | 0.625 | 0.125 |
| `DTR+V` | 39/40 | 25 / 8 / 6 | 0.725 | 0.625 | 0.150 |
| `DTRa` | 36/40 | 26 / 9 / 1 | 0.762 | 0.650 | 0.025 |
| `DTRa+V` | 39/40 | 27 / 10 / 2 | 0.800 | 0.675 | 0.050 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0. For wrong (all), a negative difference favours A.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A higher / lower |
|---|---|---|---|---|---|---|
| `S2` | `B0` | RQ1: focused skill vs his prompt | correct (all) | +0.062 [-0.075, +0.200] | 0.446 | 8/5 |
| `S2` | `B0` | RQ1: focused skill vs his prompt | fully correct (all) | +0.050 [-0.100, +0.200] | 0.754 | 6/4 |
| `S2` | `B0` | RQ1: focused skill vs his prompt | wrong (all) | -0.025 [-0.125, +0.050] | 1.000 | 1/2 |
| `S1` | `B0` | RQ1: whole skill in the system prompt vs his prompt | correct (all) | +0.050 [-0.062, +0.175] | 0.465 | 7/5 |
| `S1` | `B0` | RQ1: whole skill in the system prompt vs his prompt | fully correct (all) | +0.025 [-0.100, +0.175] | 1.000 | 5/4 |
| `S1` | `B0` | RQ1: whole skill in the system prompt vs his prompt | wrong (all) | +0.000 [-0.075, +0.075] | 1.000 | 1/1 |
| `S3` | `B0` | RQ1: comprehensive skill vs his prompt | correct (all) | -0.013 [-0.138, +0.113] | 0.929 | 6/9 |
| `S3` | `B0` | RQ1: comprehensive skill vs his prompt | fully correct (all) | -0.075 [-0.250, +0.075] | 0.549 | 4/7 |
| `S3` | `B0` | RQ1: comprehensive skill vs his prompt | wrong (all) | -0.025 [-0.100, +0.050] | 1.000 | 1/2 |
| `S4` | `B0` | RQ1: skill written by the model itself vs his prompt | correct (all) | +0.025 [-0.087, +0.138] | 0.652 | 5/5 |
| `S4` | `B0` | RQ1: skill written by the model itself vs his prompt | fully correct (all) | -0.050 [-0.200, +0.075] | 0.727 | 3/5 |
| `S4` | `B0` | RQ1: skill written by the model itself vs his prompt | wrong (all) | -0.050 [-0.125, +0.000] | 0.500 | 0/2 |
| `S2` | `S3` | RQ1: focused vs comprehensive skill | correct (all) | +0.075 [-0.025, +0.188] | 0.285 | 9/4 |
| `S2` | `S3` | RQ1: focused vs comprehensive skill | fully correct (all) | +0.125 [-0.025, +0.300] | 0.227 | 8/3 |
| `S2` | `S3` | RQ1: focused vs comprehensive skill | wrong (all) | +0.000 [-0.100, +0.100] | 1.000 | 2/2 |
| `V` | `B0` | RQ2: validation retry vs his single call | correct (all) | +0.050 [+0.000, +0.113] | 0.250 | 3/0 |
| `V` | `B0` | RQ2: validation retry vs his single call | fully correct (all) | +0.025 [+0.000, +0.075] | – | 1/0 |
| `V` | `B0` | RQ2: validation retry vs his single call | wrong (all) | +0.000 [+0.000, +0.000] | – | 0/0 |
| `DTR` | `B0` | RQ2: Deep Tax Research vs his deployed context | correct (all) | -0.013 [-0.163, +0.125] | 0.831 | 8/8 |
| `DTR` | `B0` | RQ2: Deep Tax Research vs his deployed context | fully correct (all) | -0.050 [-0.225, +0.125] | 0.593 | 6/8 |
| `DTR` | `B0` | RQ2: Deep Tax Research vs his deployed context | wrong (all) | +0.050 [-0.075, +0.175] | 0.688 | 4/2 |
| `DTR` | `B1` | RQ2: Deep Tax Research vs R6y alone | correct (all) | -0.037 [-0.175, +0.100] | 0.580 | 6/8 |
| `DTR` | `B1` | RQ2: Deep Tax Research vs R6y alone | fully correct (all) | -0.075 [-0.250, +0.100] | 0.581 | 5/8 |
| `DTR` | `B1` | RQ2: Deep Tax Research vs R6y alone | wrong (all) | +0.075 [-0.050, +0.200] | 0.453 | 5/2 |
| `B1` | `B0` | R6y vs his deployed context (this round) | correct (all) | +0.025 [-0.075, +0.113] | 0.789 | 5/3 |
| `B1` | `B0` | R6y vs his deployed context (this round) | fully correct (all) | +0.025 [-0.100, +0.150] | 1.000 | 4/3 |
| `B1` | `B0` | R6y vs his deployed context (this round) | wrong (all) | -0.025 [-0.075, +0.000] | – | 0/1 |
| `B0w` | `B0` | control: his retrieval with 4,000 tokens instead of 2,500 | correct (all) | +0.000 [-0.138, +0.138] | 1.000 | 7/6 |
| `B0w` | `B0` | control: his retrieval with 4,000 tokens instead of 2,500 | fully correct (all) | -0.025 [-0.200, +0.150] | 1.000 | 5/6 |
| `B0w` | `B0` | control: his retrieval with 4,000 tokens instead of 2,500 | wrong (all) | -0.050 [-0.125, +0.000] | 0.500 | 0/2 |
| `DTR` | `B0w` | Deep Tax Research vs simply more of his own ranking | correct (all) | -0.013 [-0.150, +0.125] | 0.883 | 7/8 |
| `DTR` | `B0w` | Deep Tax Research vs simply more of his own ranking | fully correct (all) | -0.025 [-0.200, +0.150] | 0.796 | 7/8 |
| `DTR` | `B0w` | Deep Tax Research vs simply more of his own ranking | wrong (all) | +0.100 [-0.025, +0.225] | 0.219 | 5/1 |
| `DTRa` | `DTR` | RQ2: research agent vs fixed research pipeline | correct (all) | +0.037 [-0.100, +0.175] | 0.599 | 10/8 |
| `DTRa` | `DTR` | RQ2: research agent vs fixed research pipeline | fully correct (all) | +0.025 [-0.150, +0.200] | 0.796 | 8/7 |
| `DTRa` | `DTR` | RQ2: research agent vs fixed research pipeline | wrong (all) | **-0.100 [-0.200, -0.025]** | 0.125 | 0/4 |
| `DTR+V` | `DTR` | RQ2: validation retry on Deep Tax Research | correct (all) | +0.000 [+0.000, +0.000] | – | 0/0 |
| `DTR+V` | `DTR` | RQ2: validation retry on Deep Tax Research | fully correct (all) | +0.000 [+0.000, +0.000] | – | 0/0 |
| `DTR+V` | `DTR` | RQ2: validation retry on Deep Tax Research | wrong (all) | +0.025 [+0.000, +0.075] | – | 1/0 |
| `DTRa+V` | `DTRa` | RQ2: validation retry on the research agent | correct (all) | +0.037 [+0.000, +0.100] | 0.500 | 2/0 |
| `DTRa+V` | `DTRa` | RQ2: validation retry on the research agent | fully correct (all) | +0.025 [+0.000, +0.075] | – | 1/0 |
| `DTRa+V` | `DTRa` | RQ2: validation retry on the research agent | wrong (all) | +0.025 [+0.000, +0.075] | – | 1/0 |

Primary comparisons (protocol): correct (all), Wilcoxon p and its Holm adjustment over the three.

| A | B | Mean A − B [95% CI] | Wilcoxon p | Holm p |
|---|---|---|---|---|
| `S2` | `B0` | +0.062 [-0.075, +0.200] | 0.446 | 0.893 |
| `V` | `B0` | +0.050 [+0.000, +0.113] | 0.250 | 0.750 |
| `DTR` | `B0` | -0.013 [-0.163, +0.125] | 0.831 | 0.893 |
