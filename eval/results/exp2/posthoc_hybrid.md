# Post-hoc hybrid: rules plus the LLM's semantic flags (exploratory)

Designed after the Experiment 2 test results were seen, so treat it as a hypothesis for the next frozen test set, not a result. No new model calls: H-det's output on each request and seed, plus the first `unsupported_clause` flag from the named LLM run, route recomputed by the policy. Means over the 90 test requests (seeds averaged), 95% bootstrap CIs.

| Variant | success | defect_recall | false_alarm_on_clean | route_correct | ask_recall | detect_unsupported_clause |
|---|---|---|---|---|---|---|
| H-det (reference) | 0.444 [0.34, 0.54] | 0.793 [0.68, 0.90] | 0.000 [0.00, 0.00] | 0.889 [0.82, 0.94] | 0.687 [0.61, 0.76] | 0.000 [0.00, 0.00] |
| H-det + H0 unsupported flags | 0.419 [0.32, 0.51] | 0.984 [0.96, 1.00] | 0.367 [0.27, 0.48] | 0.778 [0.70, 0.85] | 0.687 [0.61, 0.76] | 0.933 [0.83, 1.00] |
| H-det + H1 unsupported flags | 0.333 [0.24, 0.43] | 1.000 [1.00, 1.00] | 0.653 [0.54, 0.77] | 0.696 [0.61, 0.77] | 0.687 [0.61, 0.76] | 1.000 [1.00, 1.00] |
| H-det + H3b unsupported flags | 0.470 [0.37, 0.57] | 0.902 [0.82, 0.98] | 0.102 [0.05, 0.16] | 0.889 [0.83, 0.94] | 0.687 [0.61, 0.76] | 0.533 [0.27, 0.80] |
