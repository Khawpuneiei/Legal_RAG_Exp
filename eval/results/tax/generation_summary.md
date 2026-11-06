# TaxRAG answers (qwen2.5:7b, the teammate's prompt and citation checker)

Citation precision: share of an answer's citations that point at a gold unit (his metric). Gold cited: share of the question's gold units the answer cites, over answered answerable questions. Gold cited (all): the same over every answerable question, a refusal counting as 0, so a configuration cannot score higher by answering less.

## Teammate's 28 questions

| Configuration | Answerable answered | Out-of-scope refused | Citation precision | Gold cited | Gold cited (all) | Model calls | Source tokens |
|---|---|---|---|---|---|---|---|
| `teammate-improved@bge-m3` | 18/25 | 3/3 | 0.452 | 0.472 | 0.340 | 28/28 | 2834 |
| `R5@budget` | 22/25 | 3/3 | 0.472 | 0.591 | 0.520 | 28/28 | 2394 |
| `R6d` | 20/25 | 3/3 | 0.402 | 0.525 | 0.420 | 28/28 | 2483 |
| `R6d+gate` | 17/25 | 3/3 | 0.468 | 0.588 | 0.400 | 20/28 | 2483 |
| `R5+expand` | 19/25 | 3/3 | 0.466 | 0.570 | 0.433 | 28/28 | 2976 |
| `R6x` | 19/25 | 3/3 | 0.473 | 0.544 | 0.413 | 28/28 | 2838 |
| `teammate-improved@gemini` | 21/25 | 3/3 | 0.539 | 0.627 | 0.527 | 28/28 | 2886 |
| `teammate-improved@gemini+gate` | 20/25 | 3/3 | 0.556 | 0.633 | 0.507 | 24/28 | 2886 |
| `R6d@gemini` | 21/25 | 3/3 | 0.458 | 0.556 | 0.467 | 28/28 | 2484 |
| `R6x@gemini` | 22/25 | 3/3 | 0.484 | 0.674 | 0.593 | 28/28 | 2769 |
| `R6y@gemini` | 20/25 | 3/3 | 0.536 | 0.650 | 0.520 | 28/28 | 2776 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A better / worse |
|---|---|---|---|---|---|---|
| `R6x@gemini` | `teammate-improved@gemini` | A* dependencies in place of his expansion, his deployed setup otherwise | gold cited (all) | +0.067 [-0.027, +0.187] | 0.500 | 2/1 |
| `R6x@gemini` | `teammate-improved@gemini` | A* dependencies in place of his expansion, his deployed setup otherwise | answered | +0.040 [+0.000, +0.120] | – | 1/0 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | gold cited (all) | -0.007 [-0.134, +0.113] | 1.000 | 2/2 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | answered | -0.040 [-0.160, +0.080] | 1.000 | 1/2 |
| `R6d@gemini` | `teammate-improved@gemini` | A* evidence in place of his whole context, on his Gemini ranking | gold cited (all) | -0.060 [-0.200, +0.073] | 0.531 | 2/4 |
| `R6d@gemini` | `teammate-improved@gemini` | A* evidence in place of his whole context, on his Gemini ranking | answered | +0.000 [-0.200, +0.200] | 1.000 | 3/3 |
| `teammate-improved@gemini+gate` | `teammate-improved@gemini` | the abstention gate on his deployed retrieval | gold cited (all) | -0.020 [-0.060, +0.000] | – | 0/1 |
| `teammate-improved@gemini+gate` | `teammate-improved@gemini` | the abstention gate on his deployed retrieval | answered | -0.040 [-0.120, +0.000] | – | 0/1 |
| `R5@budget` | `teammate-improved@bge-m3` | Experiment 3 retrieval (R5) vs his `improved`, same local embedder | gold cited (all) | **+0.180 [+0.033, +0.333]** | 0.031 | 7/2 |
| `R5@budget` | `teammate-improved@bge-m3` | Experiment 3 retrieval (R5) vs his `improved`, same local embedder | answered | +0.160 [+0.000, +0.360] | 0.219 | 5/1 |
| `R5+expand` | `teammate-improved@bge-m3` | R5 vs his `improved`, same local embedder and context layout (hits + his expansion) | gold cited (all) | +0.093 [-0.073, +0.267] | 0.312 | 5/3 |
| `R5+expand` | `teammate-improved@bge-m3` | R5 vs his `improved`, same local embedder and context layout (hits + his expansion) | answered | +0.040 [-0.120, +0.200] | 1.000 | 3/2 |
| `R5@budget` | `R5+expand` | his one-hop expansion removed, R5 hits | gold cited (all) | +0.087 [-0.040, +0.207] | 0.312 | 5/1 |
| `R5@budget` | `R5+expand` | his one-hop expansion removed, R5 hits | answered | +0.120 [-0.040, +0.280] | 0.375 | 4/1 |
| `R6x` | `R5+expand` | A* dependencies vs his expansion, after the R5 hits | gold cited (all) | -0.020 [-0.120, +0.067] | 1.000 | 2/2 |
| `R6x` | `R5+expand` | A* dependencies vs his expansion, after the R5 hits | answered | +0.000 [-0.160, +0.160] | 1.000 | 2/2 |
| `R6d` | `R5@budget` | A* evidence vs flat R5, same budget | gold cited (all) | -0.100 [-0.260, +0.067] | 0.324 | 3/7 |
| `R6d` | `R5@budget` | A* evidence vs flat R5, same budget | answered | -0.080 [-0.240, +0.040] | 0.625 | 1/3 |
| `R6d+gate` | `R6d` | the abstention gate on R6d | gold cited (all) | -0.020 [-0.060, +0.000] | – | 0/1 |
| `R6d+gate` | `R6d` | the abstention gate on R6d | answered | -0.120 [-0.241, +0.000] | 0.250 | 0/3 |

## Held-out test split

| Configuration | Answerable answered | Out-of-scope refused | Citation precision | Gold cited | Gold cited (all) | Model calls | Source tokens |
|---|---|---|---|---|---|---|---|
| `teammate-improved@bge-m3` | 58/79 | 20/20 | 0.629 | 0.681 | 0.500 | 99/99 | 2879 |
| `R5@budget` | 68/79 | 20/20 | 0.543 | 0.701 | 0.603 | 99/99 | 2358 |
| `R6d` | 52/79 | 20/20 | 0.631 | 0.801 | 0.527 | 99/99 | 2482 |
| `R6d+gate` | 44/79 | 20/20 | 0.679 | 0.837 | 0.466 | 66/99 | 2482 |
| `R5+expand` | 61/79 | 20/20 | 0.606 | 0.751 | 0.580 | 99/99 | 2828 |
| `R6x` | 60/79 | 20/20 | 0.589 | 0.758 | 0.576 | 99/99 | 2799 |
| `teammate-improved@gemini` | 66/79 | 20/20 | 0.558 | 0.730 | 0.610 | 99/99 | 2750 |
| `teammate-improved@gemini+gate` | 61/79 | 20/20 | 0.566 | 0.740 | 0.572 | 79/99 | 2750 |
| `R6d@gemini` | 57/79 | 20/20 | 0.517 | 0.719 | 0.519 | 99/99 | 2476 |
| `R6x@gemini` | 65/79 | 20/20 | 0.588 | 0.759 | 0.624 | 99/99 | 2773 |
| `R6y@gemini` | 64/79 | 20/20 | 0.588 | 0.771 | 0.624 | 99/99 | 2768 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A better / worse |
|---|---|---|---|---|---|---|
| `R6x@gemini` | `teammate-improved@gemini` | A* dependencies in place of his expansion, his deployed setup otherwise | gold cited (all) | +0.015 [-0.053, +0.080] | 0.666 | 11/6 |
| `R6x@gemini` | `teammate-improved@gemini` | A* dependencies in place of his expansion, his deployed setup otherwise | answered | -0.013 [-0.076, +0.051] | 1.000 | 3/4 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | gold cited (all) | +0.015 [-0.051, +0.078] | 0.674 | 8/5 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | answered | -0.025 [-0.076, +0.025] | 0.625 | 1/3 |
| `R6d@gemini` | `teammate-improved@gemini` | A* evidence in place of his whole context, on his Gemini ranking | gold cited (all) | -0.091 [-0.215, +0.032] | 0.174 | 11/19 |
| `R6d@gemini` | `teammate-improved@gemini` | A* evidence in place of his whole context, on his Gemini ranking | answered | -0.114 [-0.228, +0.000] | 0.050 | 6/15 |
| `teammate-improved@gemini+gate` | `teammate-improved@gemini` | the abstention gate on his deployed retrieval | gold cited (all) | -0.038 [-0.089, +0.000] | 0.250 | 0/3 |
| `teammate-improved@gemini+gate` | `teammate-improved@gemini` | the abstention gate on his deployed retrieval | answered | **-0.063 [-0.127, -0.013]** | 0.062 | 0/5 |
| `R5@budget` | `teammate-improved@bge-m3` | Experiment 3 retrieval (R5) vs his `improved`, same local embedder | gold cited (all) | **+0.103 [+0.019, +0.196]** | 0.022 | 15/7 |
| `R5@budget` | `teammate-improved@bge-m3` | Experiment 3 retrieval (R5) vs his `improved`, same local embedder | answered | **+0.127 [+0.038, +0.215]** | 0.008 | 12/2 |
| `R5+expand` | `teammate-improved@bge-m3` | R5 vs his `improved`, same local embedder and context layout (hits + his expansion) | gold cited (all) | +0.080 [-0.006, +0.169] | 0.053 | 14/8 |
| `R5+expand` | `teammate-improved@bge-m3` | R5 vs his `improved`, same local embedder and context layout (hits + his expansion) | answered | +0.038 [-0.038, +0.114] | 0.549 | 7/4 |
| `R5@budget` | `R5+expand` | his one-hop expansion removed, R5 hits | gold cited (all) | +0.023 [-0.046, +0.093] | 0.546 | 7/5 |
| `R5@budget` | `R5+expand` | his one-hop expansion removed, R5 hits | answered | **+0.089 [+0.025, +0.165]** | 0.039 | 8/1 |
| `R6x` | `R5+expand` | A* dependencies vs his expansion, after the R5 hits | gold cited (all) | -0.004 [-0.070, +0.059] | 0.879 | 7/6 |
| `R6x` | `R5+expand` | A* dependencies vs his expansion, after the R5 hits | answered | -0.013 [-0.089, +0.063] | 1.000 | 4/5 |
| `R6d` | `R5@budget` | A* evidence vs flat R5, same budget | gold cited (all) | -0.076 [-0.156, +0.004] | 0.049 | 7/13 |
| `R6d` | `R5@budget` | A* evidence vs flat R5, same budget | answered | **-0.203 [-0.304, -0.126]** | 0.000 | 0/16 |
| `R6d+gate` | `R6d` | the abstention gate on R6d | gold cited (all) | **-0.061 [-0.118, -0.017]** | 0.031 | 0/6 |
| `R6d+gate` | `R6d` | the abstention gate on R6d | answered | **-0.101 [-0.177, -0.038]** | 0.008 | 0/8 |

## Held-out dev split (run after the first test run, to check the R6x variant on unseen answers)

| Configuration | Answerable answered | Out-of-scope refused | Citation precision | Gold cited | Gold cited (all) | Model calls | Source tokens |
|---|---|---|---|---|---|---|---|
| `R5+expand` | 30/40 | 10/10 | 0.641 | 0.867 | 0.650 | 50/50 | 2797 |
| `R6x` | 31/40 | 10/10 | 0.750 | 0.860 | 0.667 | 50/50 | 2774 |
| `teammate-improved@gemini` | 34/40 | 9/10 | 0.556 | 0.784 | 0.667 | 50/50 | 2760 |
| `R6d@gemini` | 29/40 | 10/10 | 0.482 | 0.701 | 0.508 | 50/50 | 2450 |
| `R6x@gemini` | 33/40 | 9/10 | 0.609 | 0.747 | 0.617 | 50/50 | 2757 |
| `R6y@gemini` | 35/40 | 9/10 | 0.550 | 0.719 | 0.629 | 50/50 | 2760 |

Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. **Bold**: the CI excludes 0.

| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A better / worse |
|---|---|---|---|---|---|---|
| `R6x@gemini` | `teammate-improved@gemini` | A* dependencies in place of his expansion, his deployed setup otherwise | gold cited (all) | -0.050 [-0.175, +0.075] | 0.590 | 3/6 |
| `R6x@gemini` | `teammate-improved@gemini` | A* dependencies in place of his expansion, his deployed setup otherwise | answered | -0.025 [-0.125, +0.050] | 1.000 | 1/2 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | gold cited (all) | -0.037 [-0.163, +0.075] | 0.688 | 3/5 |
| `R6y@gemini` | `teammate-improved@gemini` | dependency-only A* in place of his expansion, his deployed setup otherwise | answered | +0.025 [-0.050, +0.100] | 1.000 | 2/1 |
| `R6d@gemini` | `teammate-improved@gemini` | A* evidence in place of his whole context, on his Gemini ranking | gold cited (all) | -0.158 [-0.325, +0.025] | 0.122 | 4/12 |
| `R6d@gemini` | `teammate-improved@gemini` | A* evidence in place of his whole context, on his Gemini ranking | answered | -0.125 [-0.275, +0.025] | 0.180 | 2/7 |
| `R6x` | `R5+expand` | A* dependencies vs his expansion, after the R5 hits | gold cited (all) | +0.017 [-0.075, +0.113] | 0.906 | 4/3 |
| `R6x` | `R5+expand` | A* dependencies vs his expansion, after the R5 hits | answered | +0.025 [-0.050, +0.125] | 1.000 | 2/1 |

