# Deployed configuration (free tier) on the frozen test split

Search `supabase-hybrid-gte-small` (Supabase Edge Function gte-small + Postgres full-text/pgvector RRF), drafting mode `rules` (no LLM), calibration lo=0.78, hi=0.9, tau=1.0 (dev split). 90 test requests; deterministic, so one run. Brackets: 95% bootstrap CIs over requests.

| Metric | Deployed | 
|---|---|
| retrieval nDCG@10 (whole request) | 0.276 [0.219, 0.336] |
| retrieval Recall@5 (whole request) | 0.298 [0.221, 0.375] |
| success | 0.356 [0.256, 0.467] |
| success_core | 0.356 [0.256, 0.467] |
| defect_recall | 0.793 [0.683, 0.902] |
| false_alarm_on_clean | 0.000 [0.000, 0.000] |
| route_correct | 0.867 [0.789, 0.933] |
| field_accuracy | 1.000 [1.000, 1.000] |
| ask_recall | 0.587 [0.510, 0.669] |
| citation_accuracy | 0.520 [0.443, 0.601] |
| hallucinated_clause_rate | 0.000 [0.000, 0.000] |
| detect_unsupported_clause | 0.000 [0.000, 0.000] |
