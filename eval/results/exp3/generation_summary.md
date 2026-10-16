# Experiment 3: generation and grounding (synthetic test subset)

30 requests from the held-out test split (seeded sample, 5 contain an ask the library cannot satisfy), 3 seeds each, temperature 0.3, model qwen2.5:7b via Ollama. Per-request means are averaged over seeds, then over requests; brackets are 95% bootstrap CIs over requests.

| Condition | citation_accuracy | hallucinated_rate | claim_support | ask_recall | abstention | n_selections | context_clauses | latency_s |
|---|---|---|---|---|---|---|---|---|
| R0 | – | 0.989 [0.967, 1.000] | – | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 2.1 | 0.0 | 6.9 |
| R1 | 0.475 [0.312, 0.637] | 0.055 [0.015, 0.106] | 0.937 [0.849, 0.992] | 0.397 [0.250, 0.542] | 1.000 [1.000, 1.000] | 2.6 | 32.1 | 7.8 |
| R4 | 0.576 [0.416, 0.733] | 0.011 [0.000, 0.033] | 0.948 [0.897, 0.987] | 0.510 [0.367, 0.659] | 1.000 [1.000, 1.000] | 3.0 | 5.0 | 6.9 |
| R5 | 0.548 [0.385, 0.700] | 0.017 [0.000, 0.050] | 0.939 [0.875, 0.993] | 0.524 [0.375, 0.667] | 1.000 [1.000, 1.000] | 2.8 | 5.0 | 6.6 |

Metric definitions are in the docstring of `eval/generation_eval.py`. R0 has no library, so its citation metrics are undefined and every drafted clause counts as not traceable to the library.
