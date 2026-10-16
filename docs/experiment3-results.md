# Experiment 3: retrieval pipeline vs no RAG vs naive RAG — results

**Run date:** 16 October 2026 · **Machine:** Windows 11 laptop, RTX 4060 (8 GB), 16 GB RAM · **Code:** this repository (`eval/run_experiment.py`, `eval/generation_eval.py`) · **Raw outputs:** `eval/results/exp3/`

## Answer to RQ3 in one paragraph

Yes. A stronger retrieval pipeline beats naive RAG by a wide margin on our use case. On the synthetic clause library, nDCG@10 rises from 0.19 (R1) to 0.51 with hybrid search plus a reranker (R4). It reaches 0.54 with contextual enrichment (R5), which also lifts Recall@5 from 0.36 to 0.49. On public data, the single biggest and most consistent lever is **contextual enrichment**: summary-augmented chunks roughly double LegalBench-RAG recall at an equal budget (0.35 → 0.63) and triple precision@1. **Reranking** helps on all three datasets. **Hybrid BM25** helps on our conversational requests but *hurts* on LegalBench-RAG. **Swapping the embedder** (R4e) helps a little: significant only on LegalBench-RAG. **LLM query rewriting** with a local 7B model (R4q) does not help and is significantly worse on two of three datasets. Clause-graph expansion with **A\*** makes the evidence set almost self-contained (definition coverage rises from 0.33 to 0.97 at the same token budget) without a significant loss of the requested clauses. It does not beat plain BFS on definition coverage, as we had hypothesised. In generation, on all 90 test requests, R4 lets the 7B drafter satisfy significantly more of the requested asks than naive RAG (ask recall 0.52 vs 0.34), with a sixth of the context. Its gains in citation accuracy and hallucination rate are not significant. Every retrieval condition correctly declines all of the 10 unsupported asks.

Every claim below is backed by a paired test in [`eval/results/exp3/significance.md`](../eval/results/exp3/significance.md). "Significant" means the 95% paired bootstrap CI of the difference excludes zero.

## Results

### Synthetic clause library (90 held-out requests; 84 have a gold clause)

| Condition | Recall@1 | Recall@5 | MRR | nDCG@10 | Tokens in top-5 |
|---|---|---|---|---|---|
| Ref-BM25 | 0.213 | 0.420 | 0.561 | 0.469 | 313 |
| R1 naive (fixed chunks, dense) | 0.184 | 0.371 | 0.428 | **0.192** | **2,088** |
| R2 clause chunks, dense | 0.070 | 0.239 | 0.291 | 0.284 | 368 |
| R3 + BM25 hybrid | 0.149 | 0.422 | 0.464 | 0.439 | 355 |
| R4 + reranker | 0.217 | 0.358 | 0.537 | 0.511 | 344 |
| R4e Qwen3-Embedding-0.6B | 0.220 | 0.361 | 0.551 | 0.519 | 345 |
| R4q + query rewrite | 0.194 | 0.341 | 0.467 | 0.454 | 323 |
| **R5 + contextual chunks** | **0.237** | **0.488** | **0.603** | **0.536** | 345 |

![Synthetic nDCG@10](../eval/results/exp3/figures/synthetic_ndcg10.png)

- **Naive RAG is the worst way to feed the drafter.** R1's top-5 chunks carry about 6× more tokens than any clause-level condition (2,088 vs about 345), and its clause ranking is poor (nDCG@10 0.19). R4 beats it by +0.32 nDCG@10 [+0.25, +0.39].
- **Dense retrieval alone fails on staff language.** BGE-M3 on clause chunks (R2) scores below BM25 alone. Staff requests are long, chatty, and paraphrase the legal concept. Adding BM25 (+0.155) and then the reranker (+0.072) are both significant.
- **Contextual chunk enrichment (R5)** lifts Recall@5 by +0.130 [+0.062, +0.205], so more of the requested clauses appear together in the top 5. Its nDCG@10 gain (+0.025) is not significant.
- **R4e** (Qwen3-Embedding-0.6B): +0.008, not significant. The reranker re-orders the top 50 anyway, which shrinks embedder differences.
- **R4q** (doctrinal rewrite): −0.057 [−0.108, −0.004], significantly worse. The 7B model's rewrite adds generic legal vocabulary that matches many clauses. This matches SG-LegalCite's own finding that *predicted* principles help far less than gold ones.

### ACORD (57 test queries, attorney-rated)

Scored with the paper's protocol (appendix C.5/F.1): unjudged pairs ignored, linear-gain nDCG, normalised star-precision.

| Condition | nDCG@5 | nDCG@10 | 3-star P@5 | 4-star P@5 | 5-star P@5 | MRR |
|---|---|---|---|---|---|---|
| Ref-BM25 | 0.438 | 0.443 | 0.429 | 0.325 | 0.271 | 0.451 |
| R1 dense | 0.558 | 0.554 | 0.525 | 0.368 | 0.130 | 0.607 |
| R2 dense | 0.569 | 0.574 | 0.518 | 0.379 | 0.164 | 0.608 |
| R3 hybrid | 0.554 | 0.550 | 0.539 | 0.421 | 0.302 | 0.525 |
| R4 + reranker | 0.604 | 0.581 | 0.577 | 0.449 | 0.251 | 0.640 |
| R4e Qwen3-Embedding-0.6B | **0.615** | 0.606 | **0.588** | 0.446 | 0.242 | **0.656** |
| R4q + query rewrite | 0.604 | **0.609** | 0.562 | 0.425 | **0.348** | 0.637 |
| *Paper, BM25 (Table 3)* | *0.525* | *0.540* | *0.509* | *0.389* | *0.090* | |
| *Paper, OpenAI text-embedding-3-large* | *0.621* | *0.641* | *0.586* | *0.389* | *0.110* | |
| *Paper, BM25 + GPT-4o pointwise rerank (Table 3)* | *0.769* | *0.797* | *0.811* | *0.600* | *0.172* | |

![ACORD nDCG@10](../eval/results/exp3/figures/acord_ndcg10.png)

- Our numbers sit in the paper's range. BGE-M3 dense is close to OpenAI's small embedding, and hybrid plus reranker is close to its large one. Our BM25 trails the paper's (0.443 vs 0.540), probably because of a different implementation and tokeniser.
- The reranker adds a significant +0.031. R4 vs R1 is not significant: ACORD's corpus is already one clause per document, so the chunking difference disappears.
- The paper's GPT-4o rerankers are far ahead of our 568M-parameter cross-encoder: 0.797 on BM25 candidates, and 0.812 on MiniLM candidates, its best system per the text. An **LLM reranker** is the obvious next condition if an approved API model becomes available.
- R4e (+0.025, p = 0.077) and R4q (+0.028, CI includes 0) point upward on ACORD but are not significant.

### LegalBench-RAG-mini (776 queries; 4 sources weighted equally)

| Condition | Precision@1 | Recall@4 | Recall@64 | **Recall within 8,000 chars** |
|---|---|---|---|---|
| Ref-BM25 | 0.019 | 0.060 | 0.280 | 0.150 |
| R1 fixed 2,000-char chunks | 0.056 | 0.408 | 0.773 | 0.408 |
| R2 500-char chunks, dense | 0.075 | 0.160 | 0.495 | 0.338 |
| R3 hybrid | 0.041 | 0.091 | 0.444 | 0.270 |
| R4 + reranker | 0.096 | 0.180 | 0.444 | 0.345 |
| R4e Qwen3-Embedding-0.6B | 0.099 | 0.182 | 0.469 | 0.366 |
| R4q + query rewrite | 0.072 | 0.151 | 0.445 | 0.321 |
| **R5 + SAC document summaries** | **0.288** | 0.400 | 0.741 | **0.631** |
| *Paper, RCTS + text-embedding-3-large (Table 5)* | *0.064* | *0.169* | *0.622* | |

![LegalBench-RAG recall at an equal budget](../eval/results/exp3/figures/lbr_recall_8kchars.png)

- **Reproduction check.** Our R2 (500-character structure-aware chunks, BGE-M3) gives precision@1 0.075 and recall@4 0.160, against the paper's 0.064 and 0.169 for its recursive splitter. That is close enough to trust the setup.
- **Summary-Augmented Chunking replicates strongly.** Prepending one generic ~150-character summary per document (written by the local 7B model) adds +0.285 recall at an equal budget [+0.255, +0.313] and triples precision@1 (0.096 → 0.288). This is the single largest effect in the experiment, and it matches Reuter et al.'s finding that retrieving from the wrong document is the main failure.
- **BM25 hybrid hurts here** (−0.068, significant), as SAC also found. The **reranker helps** (+0.075), contrary to LegalBench-RAG's own Cohere result (whose tables we found internally inconsistent; README 2.2).
- **Chunk size:** at the same character budget, fixed 2,000-character chunks beat 500-character chunks (+0.070). Larger chunks keep more document context. Summaries keep it better still.
- R4e is a small significant gain (+0.020). R4q is a small significant loss (−0.025).

### Clause-graph expansion (synthetic, 1,200-token budget, 84 test requests)

| Condition | Clause recall | Definition coverage | Cross-ref completeness | Legal requirements satisfied | Tokens used | Nodes expanded |
|---|---|---|---|---|---|---|
| R5@budget (flat, same budget) | **0.682** | 0.334 | 0.418 | 0.431 | 1,192 | 0 |
| R6a BFS depth 2 | 0.508 | **0.990** | **0.996** | 0.690 | 686 | 19 |
| R6b Personalized PageRank | 0.666 | 0.799 | 0.624 | 0.741 | 1,190 | 129 |
| R6c A\*, admissible h | 0.644 | 0.974 | 0.685 | 0.950 | 1,036 | 26 |
| R6d A\*, tuned h (λ = 0, μ = 2) | 0.642 | 0.984 | 0.796 | **0.979** | 1,048 | 24 |

![Graph expansion](../eval/results/exp3/figures/synthetic_graph.png)

- **A\* vs flat retrieval at the same budget.** Definition coverage rises by +0.639 [+0.584, +0.693] and requirement satisfaction from 0.43 to 0.95. Clause recall changes by −0.038, which is not significant. The drafter receives the clause *and* the definitions and linked clauses it depends on.
- **Hypotheses (README 2.4.4), as written before the run:**
  - "R6c beats R6a on definition coverage and cross-reference completeness at equal budget": **rejected**. BFS scores higher on both (0.990 / 0.996 vs 0.974 / 0.685). BFS gets there by spending its budget on the dependencies of a few seeds. Its clause recall (0.508) and requirement satisfaction (0.690) are significantly lower than A\*'s (+0.135 and +0.260 for A\*), and it uses only 686 tokens.
  - "R6c expands fewer nodes than R6a and R6b": **partly true**. A\* expands 26 nodes against PageRank's 129, but BFS's 19 is fewer.
- **The tuned heuristic is inadmissible and better.** λ = 0 and μ = 2, chosen on the dev split, add +0.111 cross-reference completeness [+0.023, +0.198] over the admissible setting. This agrees with Distance-Indexed Neural A\* (README 2.2): when hard structure bounds the search, admissibility buys nothing in practice.

### Generation and grounding (all 90 held-out requests × 3 seeds, qwen2.5:7b)

| Condition | Clauses shown | Citation accuracy | Ask recall | Hallucinated-clause rate | Claim support (verbatim quote) |
|---|---|---|---|---|---|
| R0 no retrieval | 0 | – | 0.000 | 0.995 [0.986, 1.000] | – |
| R1 naive RAG | 31.3 | 0.493 [0.386, 0.599] | 0.340 [0.256, 0.430] | 0.019 [0.002, 0.046] | 0.955 [0.914, 0.987] |
| R4 hybrid + reranker | 5 | **0.617** [0.533, 0.703] | 0.521 [0.431, 0.611] | 0.008 [0.000, 0.019] | 0.969 [0.946, 0.989] |
| R5 + contextual chunks | 5 | 0.606 [0.512, 0.694] | **0.556** [0.466, 0.643] | **0.006** [0.000, 0.015] | **0.971** [0.945, 0.992] |

Unsupported asks, per requirement (the 10 test requests that contain one, × 3 seeds). Each row's four outcomes sum to 1:

| Condition | Correct abstention | False citation | Drafted a clause instead | Omitted the ask | Old item-level metric (lenient) |
|---|---|---|---|---|---|
| R0 no retrieval | 0.00 | 0.00 | 1.00 | 0.00 | 1.00 |
| R1 naive RAG | **1.00** | 0.00 | 0.00 | 0.00 | 1.00 |
| R4 hybrid + reranker | **1.00** | 0.00 | 0.00 | 0.00 | 1.00 |
| R5 + contextual chunks | **1.00** | 0.00 | 0.00 | 0.00 | 1.00 |

- **Retrieval is what makes citation possible at all.** Without the library (R0), essentially every clause the model writes is untraceable to an approved clause (0.995). Naive RAG brings this down to 0.019, a difference of −0.976 [−0.996, −0.948].
- **R4 vs R1 on the full split: only ask recall is significant.**
  - **Ask recall: +0.181 [+0.073, +0.285], Wilcoxon p = 0.002 (n = 84 requests with a supported ask).** With hybrid search and the reranker, the drafter satisfies about half of the requested asks instead of a third, using one sixth of naive RAG's context (5 clauses vs 31).
  - Citation accuracy: +0.114 [−0.007, +0.241], p = 0.071 (n = 60 requests where both conditions cite something). It points the same way, but the CI still includes zero.
  - Hallucinated-clause rate: −0.011 [−0.042, +0.010]. Not significant; both conditions are near zero.
  - Claim support: +0.011 [−0.035, +0.068]. Not significant; both conditions are near 1.
  - Correct abstention and false citation: identical (1.00 and 0.00 in both).
- **Contextual enrichment (R5 vs R4) adds nothing significant at generation time.** Ask recall +0.035 [−0.026, +0.100], citation accuracy +0.020 [−0.042, +0.085]. R5's retrieval gain in Recall@5 does not carry through to significantly better selections with this model.
- **A scoring fix removed an apparent hallucination gap.** Naive RAG's excerpts are headed `[clause_id: X]`, and the model often copies the label, writing `clause_id: BP-DISPUTE-SG-COURTS`. This happened in 23 of R1's 605 selections and 3 each for R4 and R5. The first scorer counted these as invented ids. They now count as the library id they name, after dropping the label, brackets and case. This lowers R1's hallucinated-clause rate from 0.047 to 0.019. The R4 − R1 difference moves from −0.037 [−0.071, −0.006], which would have been reported as significant, to −0.011 [−0.042, +0.010]. R1's ask recall (0.324 → 0.340) and citation accuracy (0.480 → 0.493) rise slightly. R4 vs R1 ask recall stays significant either way.
- **When the model cites, it quotes faithfully.** 95–97% of citations carry a verbatim quote of 8 or more words from the cited clause. The errors are about *which* clause, not misquoting.
- **Per-requirement abstention: every retrieval condition declines the unsupported ask, every time.**
  - The unsupported asks are crypto custody, a Shariah undertaking, carbon credits, an ERISA representation and an Indonesian non-compete.
  - On all 30 request-seed pairs, R1, R4 and R5 left the unsupported requirement at null with no drafted text and never cited a clause for it (0 false citations).
  - R0, which is told to draft, writes a clause for every one.
  - The old item-level metric's 1.0 was therefore right here, but it could not check *which* requirement was left null.
- **The alignment behind the abstention metric was checked by hand.**
  - All 120 unsupported-ask alignments (10 requests × 3 seeds × 4 conditions) match the model's own requirement line for that ask. The matched line scores at least 0.50 on the alignment's similarity scale, against at most 0.31 for any other line in the same output.
  - As a cross-check, take the selections that correctly cite the gold clause of exactly one ask. The alignment assigns 92–94% of them to that same ask, and only 1 of 652 to a different ask: a near tie where the model's own label and its citation disagree. The rest stay unaligned because their paraphrase is too loose for word overlap; this affects no abstention outcome.
- **The abstention test is too easy to separate the conditions.** It has 10 requests, and its 5 unsupported topics are far from anything in the library, so every retrieval condition is at ceiling. No difference between R1, R4 and R5 can show up, and none is claimed. The test says nothing yet about near misses, where a false citation is most likely: for example, a 24-month non-solicit when the library has only 6- and 12-month versions.

## What this means for the prototype

1. **Production retrieval configuration:** clause-level chunks with headings, hybrid BM25 + dense, cross-encoder reranker, and contextual enrichment (R5), followed by A\* clause-graph expansion with the dev-tuned heuristic (R6d), so the drafter always receives the definitions and linked clauses it depends on. This replaces "R4" in the release-gate configuration (README 1.5).
2. **Keep BM25 for staff requests, but monitor it.** It was the largest single gain on our conversational requests and a loss on LegalBench-RAG's formal queries. Re-test it on real requests.
3. **Embedder:** Qwen3-Embedding-0.6B is at least as good as BGE-M3 everywhere and significantly better on LegalBench-RAG. Switching is low-risk, but the gain is small next to the reranker and contextual chunks.
4. **Drop the doctrinal query rewrite** (R4q) unless a stronger model is approved. With a local 7B model it hurt on two datasets.
5. **Next condition to add:** an LLM reranker. ACORD shows GPT-4o-class reranking far ahead of any cross-encoder (nDCG@10 about 0.80 vs 0.58–0.61 here).
6. **Before the report:** have a second person label a sample of requests (plan section 6.1, inter-annotator agreement). Also add harder unsupported asks: near misses of library clauses rather than unrelated topics. The current 10 are at ceiling for every retrieval condition, so they cannot show whether the drafter abstains when a tempting but wrong clause is in context.

## Reproducing

See [Running Experiment 3](../README.md#running-experiment-3-locally). In short: `scripts/download_public.py`, `scripts/build_synthetic.py`, `eval/run_experiment.py`, `eval/generation_eval.py`, `eval/significance.py`, `eval/plot_results.py`. Raw per-query metrics are in `eval/results/exp3/per_query.jsonl`, rankings in `rankings.jsonl`, and generation outputs, including the model's raw JSON, in `generation_per_item.jsonl`.

## Method

### Question and hypotheses (written before running)

RQ3 from the project plan: does a stronger retrieval pipeline improve retrieval accuracy and grounding compared with no retrieval and naive RAG? The README's hypotheses (section 2.4.4) were:

- clause-level chunking + hybrid BM25/dense + reranking beats naive RAG;
- R6c (A\*) beats R6a (BFS) on definition coverage and cross-reference completeness at equal token budget, and expands fewer nodes than R6a and R6b;
- R6c does not beat R5 on ACORD (ACORD has no graph, so graph conditions are not run there).

Two further conditions came from the literature review in README 2.7:

- **R4e**: swap BGE-M3 for Qwen3-Embedding-0.6B. On MLEB, BGE-M3 scores 69.44 and Qwen3-Embedding-0.6B scores 77.13.
- **R4q**: add an LLM rewrite of the request into the clause's legal purpose, following SG-LegalCite and the Stanford Bar Exam QA work.

### Data

| Dataset | What it is | Queries used | Relevance labels |
|---|---|---|---|
| **Synthetic clause library** (`data/synthetic/`) | 129 synthetic Singapore-context clauses: 28 definitions, 54 standard, 23 fallback and 24 optional. They cover 5 templates (NDA, IMA, Distribution, Side Letter, Subscription) and are rendered into 11 documents with exact character spans. Requests are written in staff language with greetings and sign-offs, deliberately avoiding the clauses' own wording | 120 requests: 30 dev (used only to tune R6d), **90 test** (headline numbers). 112 have at least one gold clause; 15 also ask for something the library does not contain | Graded per request: 3 = the clause asked for, 2 = acceptable alternative, 1 = same clause type, other variant |
| **ACORD** (Wang et al., ACL 2025; CC BY 4.0) | 3,931 contract clauses from EDGAR and terms of service; attorney-written queries | **57 test queries** | 0–4 (1–5 stars); relevant = 4 stars or more |
| **LegalBench-RAG-mini** (Pipitone & Houir Alami, 2024) | 72 documents (NDAs, M&A agreements, commercial contracts, privacy policies), 8.68M characters | **776 queries** | Exact character spans |

LegalBench-RAG's official Dropbox folder cannot be downloaded non-interactively. `scripts/download_public.py` therefore takes the byte-exact Hugging Face copy (`awinml/legalbench-rag`) and checks all 718 files against its SHA256SUMS. It then rebuilds the mini subset with the official sampling code and stops unless the result matches the paper's Table 3 exactly. It does: 776 queries, 72 documents, 8,682,104 characters.

### Conditions

| ID | Chunking | Retriever | Extras |
|---|---|---|---|
| Ref-BM25 | clause-level | BM25 | reference only |
| R1 | fixed ~512 tokens (2,000 chars), no overlap | dense (BGE-M3) | naive RAG |
| R2 | clause-level (heading + clause; 500-char recursive split on LegalBench-RAG) | dense (BGE-M3) | |
| R3 | clause-level | hybrid: BM25 + BGE-M3, reciprocal rank fusion (k = 60) | |
| R4 | clause-level | hybrid | + cross-encoder reranker (`BAAI/bge-reranker-v2-m3`, top 50) |
| R4e | clause-level | hybrid with **Qwen3-Embedding-0.6B** | + reranker |
| R4q | clause-level | hybrid | + reranker + **doctrinal query rewrite** (qwen2.5:7b) |
| R5 | clause-level | hybrid | + reranker + contextual enrichment: per-chunk context on synthetic; SAC-style 150-character document summary on LegalBench-RAG. Not run on ACORD, whose clauses have no parent document |
| R6a–d | R5 seeds (top 5 clauses) | graph expansion over the clause graph within a 1,200-token budget | a: BFS depth 2; b: Personalized PageRank; c: A\* with admissible h (λ = 0.2, μ = 1); d: A\* with λ, μ tuned on dev |

R0 (no retrieval) has no retrieval metrics. It appears only in the generation and grounding evaluation.

### Metrics

- **Retrieval:**
  - Recall@k: share of relevant clauses covered by the top-k chunks. A chunk covers a clause if it contains at least half of the clause's characters.
  - MRR.
  - nDCG@5 and nDCG@10 over the clause ranking the chunks induce.
  - LegalBench-RAG character precision and recall at k, computed exactly as in `legalbenchrag/run_benchmark.py`, with its four sources weighted equally.
  - ACORD star-precision@5.
  - Tokens retrieved.
- **Graph (R6):** clause recall, definition coverage, cross-reference completeness, legal-requirement satisfaction, evidence tokens, nodes expanded and wall time.
- **Generation and grounding** (all 90 test requests × 3 seeds, qwen2.5:7b, temperature 0.3). The model returns one selection per requirement it sees in the request: a short requirement description, a `clause_id` (or null) and an evidence quote.
  - citation accuracy: share of cited ids that are a gold clause of one of the request's asks;
  - hallucinated-clause rate: share of selections not traceable to the library (an id that is not in the library, or drafted text with no id). An id counts as a library id if it matches one after dropping a copied `clause_id:` label, brackets and case;
  - claim support: the model's evidence quote of 8 or more words must appear verbatim in the cited clause;
  - ask recall: share of the request's asks satisfied by a correct citation;
  - **per-requirement abstention** (the 10 requests with an unsupported ask). Each selection is aligned one-to-one to the request's asks and unsupported asks by the words of its requirement description. The alignment uses IDF-weighted word overlap with the ask phrasings in `scripts/clause_catalog.py` (`ASKS`, `MISSING_ASKS`) and an optimal assignment, and never looks at which clause was cited. The unsupported ask then has one of four outcomes: **correct abstention** (its selection has a null id and no drafted text), **false citation** (its selection cites some clause), drafted (null id, but a drafted clause instead), or omitted (no selection matches it);
  - lenient abstention, the earlier item-level metric, kept for comparison: the request has *any* null selection, whichever requirement it was on.

  All are computed deterministically, with no LLM judge.
- **Uncertainty:** 95% bootstrap confidence intervals over queries (2,000 resamples).

### Limitations of this run

- The synthetic library is small (129 clauses) and written by the same team that wrote the requests, although by different code paths and phrasings. It measures the pipeline against rules we designed. It does not prove performance on real agreements.
- Every LLM step uses one local 7B model (qwen2.5:7b, 4-bit). A stronger API model would probably write better contexts, rewrites and drafts. The plan's second model family and an LLM judge were not used.
- The commercial-embedder arm of R4e was not run, because no Voyage or Isaacus key is available and spending on the OpenAI key was not authorised.
- R5 on LegalBench-RAG summarises only the head and tail of long documents (12,000 + 2,000 characters), because the local model's context is limited.
- The generation metrics score the model's selections, not finished drafts. The per-requirement alignment uses word overlap with the catalogue's ask phrasings. It was checked by hand only for the unsupported asks.
- The abstention test is small (10 requests, 5 distinct unsupported topics) and easy, because each topic is far from the library. It is at ceiling for every retrieval condition.
- Experiments 1 (skill files) and 2 (agent harness) are not part of this run.
