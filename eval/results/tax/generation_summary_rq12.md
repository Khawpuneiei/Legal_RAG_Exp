# TaxRAG RQ1 and RQ2 (qwen3:8b): answers per condition

Protocol: docs/taxrag-rq12-protocol.md. Gold cited (all): share of the question's gold units the answer cites, a refusal counting 0. Gold in context: share of the gold units the sources contain. Calls: answer + helper calls per question. Model tokens: prompt + completion tokens of those calls per question, thinking included. Seconds: model time per question. Cap: answer calls that stopped at the 2,000-token cap.

## Held-out test split

| Condition | Answerable answered | Out-of-scope refused | Citation precision | Gold cited (all) | Gold in context | Source tokens | Calls | Model tokens | Seconds | Cap | Retries |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `B0` | 71/79 | 17/20 | 0.569 | 0.776 | 0.918 | 2750 | 1.0 | 5,139 | 32 | 8 | 0 |
| `B1` | 70/79 | 19/20 | 0.586 | 0.770 | 0.926 | 2768 | 1.0 | 5,442 | 27 | 7 | 0 |
| `B0w` | 69/79 | 20/20 | 0.584 | 0.707 | 0.949 | 4394 | 1.0 | 7,552 | 32 | 5 | 0 |
| `S1` | 76/79 | 18/20 | 0.525 | 0.800 | 0.918 | 2750 | 1.0 | 10,106 | 38 | 4 | 0 |
| `S2` | 75/79 | 19/20 | 0.508 | 0.776 | 0.918 | 2750 | 2.0 | 7,495 | 36 | 5 | 0 |
| `S3` | 76/79 | 18/20 | 0.505 | 0.776 | 0.918 | 2750 | 1.0 | 10,094 | 37 | 4 | 0 |
| `S4` | 71/79 | 20/20 | 0.548 | 0.766 | 0.918 | 2750 | 1.0 | 5,498 | 32 | 7 | 0 |
| `V` | 77/79 | 17/20 | 0.570 | 0.812 | 0.918 | 2750 | 1.1 | 5,978 | 38 | 14 | 14 |
| `DTR` | 71/79 | 19/20 | 0.616 | 0.755 | 0.928 | 2778 | 3.0 | 10,297 | 47 | 8 | 0 |
| `DTR+V` | 77/79 | 19/20 | 0.593 | 0.791 | 0.928 | 2778 | 3.2 | 11,438 | 52 | 11 | 20 |
| `DTRa` | 70/79 | 20/20 | 0.567 | 0.753 | 0.916 | 2803 | 4.3 | 19,047 | 68 | 7 | 0 |
| `DTRa+V` | 77/79 | 20/20 | 0.566 | 0.812 | 0.916 | 2803 | 4.4 | 20,166 | 74 | 10 | 19 |
| `C` | 79/79 | 18/20 | 0.565 | 0.848 | 0.926 | 2768 | 2.1 | 8,534 | 29 | 3 | 11 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A better / worse |
|---|---|---|---|---|---|---|
| `S2` | `B0` | RQ1: focused skill vs his prompt | gold cited (all) | -0.000 [-0.074, +0.078] | 0.949 | 7/7 |
| `S2` | `B0` | RQ1: focused skill vs his prompt | answered | +0.051 [+0.000, +0.114] | 0.219 | 5/1 |
| `S2` | `B0` | RQ1: focused skill vs his prompt | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `S1` | `B0` | RQ1: whole skill in the system prompt vs his prompt | gold cited (all) | +0.023 [-0.049, +0.095] | 0.584 | 9/6 |
| `S1` | `B0` | RQ1: whole skill in the system prompt vs his prompt | answered | +0.063 [+0.000, +0.139] | 0.180 | 7/2 |
| `S1` | `B0` | RQ1: whole skill in the system prompt vs his prompt | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `S3` | `B0` | RQ1: comprehensive skill vs his prompt | gold cited (all) | +0.000 [-0.076, +0.074] | 0.931 | 8/7 |
| `S3` | `B0` | RQ1: comprehensive skill vs his prompt | answered | +0.063 [-0.013, +0.139] | 0.180 | 7/2 |
| `S3` | `B0` | RQ1: comprehensive skill vs his prompt | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `S4` | `B0` | RQ1: skill written by the model itself vs his prompt | gold cited (all) | -0.011 [-0.087, +0.072] | 0.744 | 9/10 |
| `S4` | `B0` | RQ1: skill written by the model itself vs his prompt | answered | +0.000 [-0.076, +0.076] | 1.000 | 4/4 |
| `S4` | `B0` | RQ1: skill written by the model itself vs his prompt | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `S2` | `S3` | RQ1: focused vs comprehensive skill | gold cited (all) | -0.000 [-0.055, +0.053] | 1.000 | 4/4 |
| `S2` | `S3` | RQ1: focused vs comprehensive skill | answered | -0.013 [-0.051, +0.025] | 1.000 | 1/2 |
| `S2` | `S3` | RQ1: focused vs comprehensive skill | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `V` | `B0` | RQ2: validation retry vs his single call | gold cited (all) | **+0.036 [+0.004, +0.078]** | 0.125 | 4/0 |
| `V` | `B0` | RQ2: validation retry vs his single call | answered | **+0.076 [+0.025, +0.139]** | 0.031 | 6/0 |
| `V` | `B0` | RQ2: validation retry vs his single call | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `DTR` | `B0` | RQ2: Deep Tax Research vs his deployed context | gold cited (all) | -0.021 [-0.089, +0.051] | 0.774 | 7/11 |
| `DTR` | `B0` | RQ2: Deep Tax Research vs his deployed context | answered | +0.000 [-0.076, +0.076] | 1.000 | 5/5 |
| `DTR` | `B0` | RQ2: Deep Tax Research vs his deployed context | gold in context | +0.011 [-0.023, +0.049] | 0.727 | 6/4 |
| `DTR` | `B1` | RQ2: Deep Tax Research vs R6y alone | gold cited (all) | -0.015 [-0.070, +0.042] | 0.749 | 7/8 |
| `DTR` | `B1` | RQ2: Deep Tax Research vs R6y alone | answered | +0.013 [-0.063, +0.089] | 1.000 | 5/4 |
| `DTR` | `B1` | RQ2: Deep Tax Research vs R6y alone | gold in context | +0.002 [-0.027, +0.032] | 1.000 | 4/3 |
| `B1` | `B0` | R6y vs his deployed context (this round) | gold cited (all) | -0.006 [-0.076, +0.061] | 0.877 | 9/9 |
| `B1` | `B0` | R6y vs his deployed context (this round) | answered | -0.013 [-0.076, +0.051] | 1.000 | 3/4 |
| `B1` | `B0` | R6y vs his deployed context (this round) | gold in context | +0.008 [-0.008, +0.030] | 0.500 | 2/1 |
| `B0w` | `B0` | control: his retrieval with 4,000 tokens instead of 2,500 | gold cited (all) | -0.070 [-0.156, +0.019] | 0.108 | 9/14 |
| `B0w` | `B0` | control: his retrieval with 4,000 tokens instead of 2,500 | answered | -0.025 [-0.101, +0.063] | 0.774 | 5/7 |
| `B0w` | `B0` | control: his retrieval with 4,000 tokens instead of 2,500 | gold in context | **+0.032 [+0.011, +0.059]** | 0.031 | 6/0 |
| `DTR` | `B0w` | Deep Tax Research vs simply more of his own ranking | gold cited (all) | +0.049 [-0.038, +0.137] | 0.209 | 12/9 |
| `DTR` | `B0w` | Deep Tax Research vs simply more of his own ranking | answered | +0.025 [-0.063, +0.114] | 0.774 | 7/5 |
| `DTR` | `B0w` | Deep Tax Research vs simply more of his own ranking | gold in context | -0.021 [-0.061, +0.021] | 0.446 | 4/8 |
| `DTRa` | `DTR` | RQ2: research agent vs fixed research pipeline | gold cited (all) | -0.002 [-0.063, +0.059] | 0.726 | 7/7 |
| `DTRa` | `DTR` | RQ2: research agent vs fixed research pipeline | answered | -0.013 [-0.089, +0.063] | 1.000 | 4/5 |
| `DTRa` | `DTR` | RQ2: research agent vs fixed research pipeline | gold in context | -0.013 [-0.057, +0.027] | 0.677 | 5/6 |
| `DTR+V` | `DTR` | RQ2: validation retry on Deep Tax Research | gold cited (all) | +0.036 [+0.000, +0.082] | 0.156 | 5/1 |
| `DTR+V` | `DTR` | RQ2: validation retry on Deep Tax Research | answered | **+0.076 [+0.025, +0.139]** | 0.031 | 6/0 |
| `DTR+V` | `DTR` | RQ2: validation retry on Deep Tax Research | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `DTRa+V` | `DTRa` | RQ2: validation retry on the research agent | gold cited (all) | **+0.059 [+0.013, +0.114]** | 0.062 | 5/0 |
| `DTRa+V` | `DTRa` | RQ2: validation retry on the research agent | answered | **+0.089 [+0.038, +0.152]** | 0.016 | 7/0 |
| `DTRa+V` | `DTRa` | RQ2: validation retry on the research agent | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `C` | `B0` | the combination chosen on dev vs his deployed setup | gold cited (all) | **+0.072 [+0.000, +0.146]** | 0.093 | 15/5 |
| `C` | `B0` | the combination chosen on dev vs his deployed setup | answered | **+0.101 [+0.038, +0.177]** | 0.008 | 8/0 |
| `C` | `B0` | the combination chosen on dev vs his deployed setup | gold in context | +0.008 [-0.008, +0.030] | 0.500 | 2/1 |

## Held-out dev split

| Condition | Answerable answered | Out-of-scope refused | Citation precision | Gold cited (all) | Gold in context | Source tokens | Calls | Model tokens | Seconds | Cap | Retries |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `B0` | 35/40 | 7/10 | 0.575 | 0.792 | 0.917 | 2760 | 1.0 | 5,102 | 32 | 2 | 0 |
| `B1` | 35/40 | 7/10 | 0.561 | 0.742 | 0.917 | 2760 | 1.0 | 5,437 | 28 | 4 | 0 |
| `B0w` | 34/40 | 8/10 | 0.574 | 0.729 | 0.942 | 4411 | 1.0 | 7,572 | 39 | 3 | 0 |
| `S1` | 38/40 | 9/10 | 0.617 | 0.808 | 0.917 | 2760 | 1.0 | 10,067 | 39 | 1 | 0 |
| `S2` | 37/40 | 9/10 | 0.595 | 0.762 | 0.917 | 2760 | 2.0 | 7,439 | 34 | 2 | 0 |
| `S3` | 36/40 | 8/10 | 0.583 | 0.754 | 0.917 | 2760 | 1.0 | 10,073 | 38 | 4 | 0 |
| `S4` | 37/40 | 7/10 | 0.568 | 0.758 | 0.917 | 2760 | 1.0 | 5,456 | 31 | 1 | 0 |
| `V` | 38/40 | 7/10 | 0.569 | 0.842 | 0.917 | 2760 | 1.2 | 6,042 | 37 | 3 | 9 |
| `DTR` | 38/40 | 8/10 | 0.565 | 0.717 | 0.854 | 2815 | 3.0 | 10,227 | 68 | 1 | 0 |
| `DTR+V` | 39/40 | 8/10 | 0.559 | 0.742 | 0.854 | 2815 | 3.1 | 10,784 | 69 | 1 | 5 |
| `DTRa` | 36/40 | 8/10 | 0.547 | 0.738 | 0.917 | 2777 | 4.4 | 19,157 | 67 | 1 | 0 |
| `DTRa+V` | 39/40 | 8/10 | 0.543 | 0.787 | 0.917 | 2777 | 4.6 | 20,011 | 70 | 1 | 8 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A better / worse |
|---|---|---|---|---|---|---|
| `S2` | `B0` | RQ1: focused skill vs his prompt | gold cited (all) | -0.029 [-0.150, +0.096] | 0.844 | 3/5 |
| `S2` | `B0` | RQ1: focused skill vs his prompt | answered | +0.050 [-0.050, +0.175] | 0.688 | 4/2 |
| `S2` | `B0` | RQ1: focused skill vs his prompt | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `S1` | `B0` | RQ1: whole skill in the system prompt vs his prompt | gold cited (all) | +0.017 [-0.083, +0.125] | 1.000 | 3/3 |
| `S1` | `B0` | RQ1: whole skill in the system prompt vs his prompt | answered | +0.075 [-0.025, +0.175] | 0.375 | 4/1 |
| `S1` | `B0` | RQ1: whole skill in the system prompt vs his prompt | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `S3` | `B0` | RQ1: comprehensive skill vs his prompt | gold cited (all) | -0.037 [-0.163, +0.087] | 0.727 | 4/6 |
| `S3` | `B0` | RQ1: comprehensive skill vs his prompt | answered | +0.025 [-0.100, +0.150] | 1.000 | 4/3 |
| `S3` | `B0` | RQ1: comprehensive skill vs his prompt | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `S4` | `B0` | RQ1: skill written by the model itself vs his prompt | gold cited (all) | -0.033 [-0.158, +0.092] | 0.766 | 3/6 |
| `S4` | `B0` | RQ1: skill written by the model itself vs his prompt | answered | +0.050 [-0.075, +0.175] | 0.688 | 4/2 |
| `S4` | `B0` | RQ1: skill written by the model itself vs his prompt | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `S2` | `S3` | RQ1: focused vs comprehensive skill | gold cited (all) | +0.008 [-0.054, +0.075] | 1.000 | 2/2 |
| `S2` | `S3` | RQ1: focused vs comprehensive skill | answered | +0.025 [-0.050, +0.125] | 1.000 | 2/1 |
| `S2` | `S3` | RQ1: focused vs comprehensive skill | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `V` | `B0` | RQ2: validation retry vs his single call | gold cited (all) | +0.050 [+0.000, +0.125] | 0.500 | 2/0 |
| `V` | `B0` | RQ2: validation retry vs his single call | answered | +0.075 [+0.000, +0.175] | 0.250 | 3/0 |
| `V` | `B0` | RQ2: validation retry vs his single call | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `DTR` | `B0` | RQ2: Deep Tax Research vs his deployed context | gold cited (all) | -0.075 [-0.217, +0.058] | 0.446 | 3/8 |
| `DTR` | `B0` | RQ2: Deep Tax Research vs his deployed context | answered | +0.075 [-0.025, +0.175] | 0.375 | 4/1 |
| `DTR` | `B0` | RQ2: Deep Tax Research vs his deployed context | gold in context | -0.062 [-0.138, +0.013] | 0.250 | 1/4 |
| `DTR` | `B1` | RQ2: Deep Tax Research vs R6y alone | gold cited (all) | -0.025 [-0.171, +0.108] | 0.795 | 5/6 |
| `DTR` | `B1` | RQ2: Deep Tax Research vs R6y alone | answered | +0.075 [-0.025, +0.176] | 0.375 | 4/1 |
| `DTR` | `B1` | RQ2: Deep Tax Research vs R6y alone | gold in context | -0.062 [-0.138, +0.013] | 0.250 | 1/4 |
| `B1` | `B0` | R6y vs his deployed context (this round) | gold cited (all) | -0.050 [-0.150, +0.050] | 0.625 | 1/3 |
| `B1` | `B0` | R6y vs his deployed context (this round) | answered | +0.000 [-0.100, +0.100] | 1.000 | 2/2 |
| `B1` | `B0` | R6y vs his deployed context (this round) | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `B0w` | `B0` | control: his retrieval with 4,000 tokens instead of 2,500 | gold cited (all) | -0.062 [-0.200, +0.075] | 0.508 | 3/6 |
| `B0w` | `B0` | control: his retrieval with 4,000 tokens instead of 2,500 | answered | -0.025 [-0.175, +0.100] | 1.000 | 3/4 |
| `B0w` | `B0` | control: his retrieval with 4,000 tokens instead of 2,500 | gold in context | +0.025 [+0.000, +0.075] | – | 1/0 |
| `DTR` | `B0w` | Deep Tax Research vs simply more of his own ranking | gold cited (all) | -0.013 [-0.158, +0.129] | 0.897 | 6/6 |
| `DTR` | `B0w` | Deep Tax Research vs simply more of his own ranking | answered | +0.100 [-0.001, +0.225] | 0.219 | 5/1 |
| `DTR` | `B0w` | Deep Tax Research vs simply more of his own ranking | gold in context | **-0.087 [-0.188, -0.013]** | 0.125 | 1/5 |
| `DTRa` | `DTR` | RQ2: research agent vs fixed research pipeline | gold cited (all) | +0.021 [-0.104, +0.150] | 0.883 | 6/4 |
| `DTRa` | `DTR` | RQ2: research agent vs fixed research pipeline | answered | -0.050 [-0.150, +0.050] | 0.625 | 1/3 |
| `DTRa` | `DTR` | RQ2: research agent vs fixed research pipeline | gold in context | +0.062 [-0.013, +0.138] | 0.250 | 4/1 |
| `DTR+V` | `DTR` | RQ2: validation retry on Deep Tax Research | gold cited (all) | +0.025 [+0.000, +0.075] | – | 1/0 |
| `DTR+V` | `DTR` | RQ2: validation retry on Deep Tax Research | answered | +0.025 [+0.000, +0.075] | – | 1/0 |
| `DTR+V` | `DTR` | RQ2: validation retry on Deep Tax Research | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |
| `DTRa+V` | `DTRa` | RQ2: validation retry on the research agent | gold cited (all) | +0.050 [+0.000, +0.125] | 0.500 | 2/0 |
| `DTRa+V` | `DTRa` | RQ2: validation retry on the research agent | answered | +0.075 [+0.000, +0.175] | 0.250 | 3/0 |
| `DTRa+V` | `DTRa` | RQ2: validation retry on the research agent | gold in context | +0.000 [+0.000, +0.000] | – | 0/0 |

