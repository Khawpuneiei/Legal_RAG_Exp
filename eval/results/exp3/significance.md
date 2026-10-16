# Experiment 3: paired comparisons

A − B on the same queries (synthetic: 90-request test split). 95% paired bootstrap CI (2,000 resamples); two-sided Wilcoxon signed-rank p-value. Differences whose CI excludes 0 are marked **bold**.

| Dataset | Metric | A | B | What changes | Mean A − B [95% CI] | Wilcoxon p | n |
|---|---|---|---|---|---|---|---|
| synthetic | ndcg@10 | R3 | R2 | Adding BM25 (hybrid) to dense clause retrieval | **+0.155 [+0.108, +0.202]** | 3.6e-08 | 84 |
| synthetic | ndcg@10 | R4 | R1 | Full pipeline (R4) vs naive RAG | **+0.319 [+0.250, +0.393]** | 1.7e-10 | 84 |
| synthetic | ndcg@10 | R4 | R3 | Adding the cross-encoder reranker | **+0.072 [+0.018, +0.123]** | 0.004 | 84 |
| synthetic | ndcg@10 | R4e | R4 | Qwen3-Embedding-0.6B vs BGE-M3 | +0.008 [-0.004, +0.024] | 0.168 | 84 |
| synthetic | ndcg@10 | R4q | R4 | Doctrinal query rewrite | **-0.057 [-0.108, -0.004]** | 0.007 | 84 |
| synthetic | ndcg@10 | R5 | R4 | Contextual chunk enrichment | +0.025 [-0.006, +0.056] | 0.122 | 84 |
| synthetic | recall@5 | R5 | R4 | Contextual chunk enrichment (Recall@5) | **+0.130 [+0.062, +0.205]** | 4.9e-04 | 84 |
| acord-test | ndcg@10 | R4 | R1 | Full pipeline vs naive RAG | +0.027 [-0.010, +0.069] | 0.191 | 57 |
| acord-test | ndcg@10 | R4 | R3 | Adding the reranker | **+0.031 [+0.010, +0.056]** | 0.003 | 57 |
| acord-test | ndcg@10 | R4e | R4 | Qwen3-Embedding-0.6B vs BGE-M3 | +0.025 [-0.003, +0.052] | 0.077 | 57 |
| acord-test | ndcg@10 | R4q | R4 | Doctrinal query rewrite | +0.028 [-0.007, +0.061] | 0.037 | 57 |
| lbr-mini | char_r@8kchars | R1 | R2 | Fixed 2,000-char vs 500-char chunks (equal budget) | **+0.070 [+0.038, +0.103]** | 1.6e-05 | 776 |
| lbr-mini | char_r@8kchars | R3 | R2 | Adding BM25 (hybrid) | **-0.068 [-0.089, -0.047]** | 7.2e-11 | 776 |
| lbr-mini | char_r@8kchars | R4 | R3 | Adding the reranker | **+0.075 [+0.055, +0.095]** | 3.6e-14 | 776 |
| lbr-mini | char_r@8kchars | R4e | R4 | Qwen3-Embedding-0.6B vs BGE-M3 | **+0.020 [+0.006, +0.037]** | 0.016 | 776 |
| lbr-mini | char_r@8kchars | R4q | R4 | Doctrinal query rewrite | **-0.025 [-0.050, -0.001]** | 0.042 | 776 |
| lbr-mini | char_r@8kchars | R5 | R4 | SAC document summaries | **+0.285 [+0.255, +0.313]** | 7.1e-57 | 776 |
| lbr-mini | char_p@1 | R5 | R4 | SAC document summaries (precision@1) | **+0.191 [+0.164, +0.220]** | 3.2e-28 | 776 |
| synthetic-graph | definition_coverage | R6c | R5@budget | A* expansion vs flat R5, same budget | **+0.639 [+0.584, +0.693]** | 1.7e-15 | 84 |
| synthetic-graph | clause_recall | R6c | R5@budget | A* expansion vs flat R5, same budget | -0.038 [-0.105, +0.029] | 0.228 | 84 |
| synthetic-graph | definition_coverage | R6c | R6a | A* vs BFS | **-0.017 [-0.031, -0.002]** | 0.033 | 84 |
| synthetic-graph | xref_completeness | R6c | R6a | A* vs BFS | **-0.311 [-0.401, -0.226]** | 2.0e-07 | 84 |
| synthetic-graph | clause_recall | R6c | R6a | A* vs BFS | **+0.135 [+0.081, +0.189]** | 8.5e-05 | 84 |
| synthetic-graph | requires_satisfied | R6c | R6a | A* vs BFS | **+0.260 [+0.151, +0.365]** | 2.0e-05 | 84 |
| synthetic-graph | xref_completeness | R6d | R6c | Tuned vs admissible heuristic | **+0.111 [+0.023, +0.198]** | 0.017 | 84 |

## Generation and grounding (30 test requests, means over 3 seeds per request)

| Metric | A | B | Mean A − B [95% CI] | Wilcoxon p | n |
|---|---|---|---|---|---|
| citation_accuracy | R4 | R1 | +0.114 [-0.058, +0.285] | 0.155 | 23 |
| ask_recall | R4 | R1 | +0.113 [-0.062, +0.280] | 0.147 | 28 |
| hallucinated_rate | R4 | R1 | -0.044 [-0.099, +0.011] | – | 29 |
| ask_recall | R5 | R4 | +0.014 [-0.129, +0.161] | – | 28 |
| citation_accuracy | R5 | R4 | -0.008 [-0.149, +0.133] | 0.953 | 25 |
| hallucinated_rate | R1 | R0 | **-0.933 [-0.980, -0.881]** | 5.5e-07 | 29 |
