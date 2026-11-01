# Integration kit for Saiharshaa/SGtax-rag

What the TaxRAG results ([docs/taxrag-results.md](../../docs/taxrag-results.md)) support adding to the teammate's repo.

## `astar-expansion.patch`: A* dependency expansion (`improved_astar`)

An opt-in retrieval config. It keeps the hits of his `improved` and replaces his one-hop `Corpus.expand` with condition R6y: an A* search over the chunks' dependency edges (cross-references, section-local definitions, earlier pieces of split provisions), cheapest first, within the same ~450 extra tokens.

- On 79 held-out test questions it resolves 0.706 of the hits' own dependencies, against 0.499 for his expansion (+0.207 [+0.174, +0.242]). Gold recall (0.926 vs 0.918) and tokens (2,766 vs 2,753) are unchanged.
- The chunks it adds bring references of their own, which the allowance cannot all cover. So the context ends with more unresolved references than his (26.0 vs 19.9, +6.1 [+3.9, +8.2]).
- Judged answer correctness does not change significantly:
  - with qwen2.5:7b, 0.506 vs 0.513, −0.006 [−0.076, +0.070];
  - with the local reasoning model qwen3:8b under his 2,000-token cap, 0.753 vs 0.728, +0.025 [−0.038, +0.089].
- It needs no embeddings. The graph is built from the chunks on first use: 0.17 s and about 8 MB for his 3,577 structured chunks, and 0.4 ms per query.
- Given the same hits, it adds exactly the same chunks as `src/tax/graph.py` (`TaxGraph.expand`, R6y) on all 177 questions: his 28 and our 149.
- His test suite passes with it (181 passed, 39 skipped, his pinned requirements).
- The new `tests/test_graph.py` (17 tests) includes expansions computed with the reference implementation. It fails under each of nine injected bugs:
  - no per-chunk budget check;
  - stopping at a chunk that does not fit instead of skipping it;
  - the heuristic's sign flipped;
  - no stop rule;
  - no token term in g;
  - edge costs swapped, and edge costs equal;
  - no "In this section" scope;
  - the hits' own edges not expanded.
- The app's default stays `improved` until the config is tested with his app's own answer models (gpt-oss-120b, Gemini Flash).

Files: new `rag/graph.py` and `tests/test_graph.py`; small changes to `rag/retrieve.py` (the config and the call), `rag/display.py` (a label), `rag/generate.py` and `scripts/search.py` (wording), and a README section. It was made on a branch `astar-expansion` of a local worktree at `ac04f49` and has not been pushed. To apply it to his repo at that commit:

```bash
git apply integrations/bc3415-tax-rag/astar-expansion.patch
```

Run that inside a checkout of his repo, with this file's path adjusted.

## `rag/rerank.py`: withdrawn

The CPU MiniLM reranker shipped here earlier. It is significantly worse than his retrieval on MRR@10 (−0.167 on his deployed Gemini retrieval), so **do not merge it**. It stays only so that conditions D1i and D3i in `eval/tax_experiment.py` can be reproduced.
