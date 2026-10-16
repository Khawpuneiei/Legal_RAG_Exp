# Experiment 3: generation and grounding (synthetic test split)

All 90 requests of the held-out test split, 10 of which contain an ask the library cannot satisfy; 3 seeds each, temperature 0.3, model qwen2.5:7b via Ollama. Per-request means are averaged over seeds, then over requests; brackets are 95% bootstrap CIs over requests.

## All requests

| Condition | citation_accuracy | hallucinated_rate | claim_support | ask_recall | n_selections | context_clauses | latency_s |
|---|---|---|---|---|---|---|---|
| R0 | – | 0.995 [0.986, 1.000] | – | 0.000 [0.000, 0.000] | 2.0 | 0.0 | 6.6 |
| R1 | 0.493 [0.386, 0.599] | 0.019 [0.002, 0.046] | 0.955 [0.914, 0.987] | 0.340 [0.256, 0.430] | 2.2 | 31.3 | 7.1 |
| R4 | 0.617 [0.533, 0.703] | 0.008 [0.000, 0.019] | 0.969 [0.946, 0.989] | 0.521 [0.431, 0.611] | 2.7 | 5.0 | 6.5 |
| R5 | 0.606 [0.512, 0.694] | 0.006 [0.000, 0.015] | 0.971 [0.945, 0.992] | 0.556 [0.466, 0.643] | 2.7 | 5.0 | 6.6 |

## Unsupported asks (10 requests, one unsupported ask each)

Per-requirement outcome of the unsupported ask (the four outcomes sum to 1), then the old item-level metric, which counts any null selection anywhere in the request.

| Condition | correct_abstention | false_citation | missing_ask_drafted | missing_ask_omitted | abstention_lenient |
|---|---|---|---|---|---|
| R0 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| R1 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| R4 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| R5 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |

Alignment check: of the selections that correctly cite the gold clause of exactly one ask, the share the text alignment assigns to that same ask (the rest stay unaligned unless noted): R1 147/157 (93.6%; 0 on another ask); R4 229/246 (93.1%; 1 on another ask); R5 228/249 (91.6%; 0 on another ask).

Metric definitions are in the docstring of `eval/generation_eval.py`. R0 has no library, so its citation metrics are undefined, every drafted clause counts as not traceable to the library, and it is told to draft rather than abstain.
