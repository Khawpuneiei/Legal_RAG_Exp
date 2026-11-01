# Experiment 3 addendum: drafting with A*-graph evidence (R6d)

90 held-out requests, seeds [1, 2, 3], qwen2.5:7b, same prompt and metrics as generation_summary.md. R4/R5 rows are the original run. Brackets: 95% bootstrap CIs over requests.

| Condition | citation_accuracy | hallucinated_rate | claim_support | ask_recall | context_clauses | correct_abstention | false_citation |
|---|---|---|---|---|---|---|---|
| R4 | 0.617 [0.533, 0.703] | 0.008 [0.000, 0.019] | 0.969 [0.946, 0.989] | 0.521 [0.431, 0.611] | 5.0 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] |
| R5 | 0.606 [0.512, 0.694] | 0.006 [0.000, 0.015] | 0.971 [0.945, 0.992] | 0.556 [0.466, 0.643] | 5.0 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] |
| R6d | 0.705 [0.620, 0.786] | 0.008 [0.000, 0.024] | 0.945 [0.909, 0.974] | 0.573 [0.493, 0.653] | 19.3 | 0.900 [0.733, 1.000] | 0.000 [0.000, 0.000] |

10 of 270 R6d replies stopped at the 700-token cap and 1 at Ollama's token repeat limit (0.40+). Either way the reply is incomplete and scores as no selections.
