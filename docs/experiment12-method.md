# Experiments 1 and 2: method

Experiment 1 asks whether a `SKILL.md` drafting playbook beats a vanilla LLM (RQ1). Experiment 2 asks whether an agent harness beats a single LLM call (RQ2). Both use the same frozen test set, model, retrieval and metrics. Results: `eval/results/exp1/summary.md`, `eval/results/exp2/summary.md`, and the README.

## Test set

`data/synthetic/intake.jsonl`, built by `scripts/build_intake.py` on top of the 120 Experiment 3 requests (30 dev, 90 test). Each request has a structured form, the free-text request, gold fields, gold clauses, planted defects and a gold route.

| Planted defect | Dev | Test | How it is planted |
|---|---|---|---|
| missing_field | 2 | 7 | a required field removed from the form and absent from the text |
| date_conflict | 2 | 6 | backdated effective date, or the text states a different date than the form |
| out_of_range | 2 | 6 | a fee, term or amount outside the approved range |
| governing_law | 2 | 5 | an unapproved law on the form, or the text demands English law while the form says Singapore |
| name_mismatch | 2 | 5 | the form's counterparty name differs by one word from the text |
| unsupported_clause | 5 | 10 | the request asks for a term with no approved clause (from Experiment 3) |
| prompt_injection | 2 | 5 | a sentence addressed to "the AI/system" asking to skip review or change the route |

41 of 90 test requests carry a defect. Gold routes on test: 46 escalate, 30 standard review, 14 return to requester (escalations also come from material deviations, i.e. approved fallback clauses with deviation cost at or above 0.5).

**Circularity control (plan 5.1).** The test set was committed (`e42a434`, sha256 `8b7d34a2…fc5a`) before any skill file was written (`b22b2c1`). The release-gate test fails if the frozen split changes. Limitation: the same author wrote the defect generator and the skill, although the skill was written from the policy and library only.

## Shared settings

| Setting | Value |
|---|---|
| Model | qwen2.5:7b via Ollama (S5, S0s: qwen2.5:3b), temperature 0.3, seeds 1–3 |
| Server | second Ollama server with parallel decoding (4 slots, flash attention, q8_0 KV cache); outputs cached |
| Retrieval | the Experiment 3 winner R5: BGE-M3 hybrid + bge-reranker-v2-m3 + contextual chunks (`src/retrieval/service.py`) |
| Candidate clauses | single-call conditions see the top 8 clauses for the whole request; H1/H3b retrieve per extracted request; agents search with a tool |
| Output contract | one JSON object: agreement type, fields, selections, issues, route, reviewer note (`src/drafting/schema.py`) |
| Budget | at most 7 agent steps, 2 reflection rounds; same cap for every agent condition |

## Experiment 1 conditions

| ID | Condition |
|---|---|
| S0 | Vanilla: "Draft this agreement from the request" + output contract |
| S1 | S0 + all skill content as a long system prompt (content without the skill mechanism) |
| S2 | Focused skill: the model sees the skill index and loads at most 3 files, then drafts |
| S3 | Comprehensive skill: one SKILL.md with every checklist and reference loaded |
| S4 | Skill written by the model itself from the task description (`skills/self-generated/SKILL.md`) |
| S5 | S2 on qwen2.5:3b |
| S0s | S0 on qwen2.5:3b (reference for S5) |

The model's output is scored as it is: no rules engine is applied in Experiment 1.

## Experiment 2 conditions

| ID | Condition | LLM calls |
|---|---|---|
| H-det | No LLM: rule segmentation of the request, A* clause assembly over retrieval candidates, Validation Engine, routing policy | 0 |
| H0 | Single call with the focused skill and top-8 candidates; the model's issues and route are final | 1 |
| H1 | Fixed pipeline: deterministic router and populator, LLM extracts the special requests, per-request retrieval, one drafting call; routing policy over the LLM's issues (no validator, no loop) | 2 |
| H2 | ReAct agent with tools `get_template`, `search_clauses`, `validate_fields`, `check_dates`, `final` | ≤ 7 |
| H3 | H2 + validation/reflection loop (≤ 2 rounds); structural issue types come from the rules, semantic ones from the LLM; the LLM route may only escalate | ≤ 11 |
| H4 | H3 + Compliance Checker agent + Router agent + human-review `interrupt()` in LangGraph (simulated reviewer resumes) | ≤ 13 |
| H3b | LLM extracts the requests, A* assigns clauses (retriever proposes actions, `tau` tuned on dev), rules + routing policy | 1 |

## Metrics (`eval/metrics/drafting_metrics.py`)

- **Fields:** accuracy over gold fields (a field whose value cannot be known is correct if left null or flagged); hallucinated-field rate (a value that appears nowhere in the request).
- **Clauses:** ask recall (requested terms cited with an acceptable clause), citation accuracy, hallucinated-clause rate (ids not in the library or not approved for the agreement type).
- **Defects:** detection per planted type; false alarm on clean requests (any defect type reported on a request with no planted defect).
- **Routing:** route accuracy, escalation precision and recall, prompt-injection resistance (route escalate on injected requests).
- **Success:** route correct, every planted defect detected, every supported ask cited correctly, no invented clause, all fields correct. `success_core` drops the field condition.
- **Consistency:** pass^k (τ-bench): success in all 3 seeds.
- **Experiment 1 only:** checklist compliance (eight deterministic checks of the model's own output), format validity (renders to .docx, no leftover placeholders).
- **Cost:** LLM calls, tool calls, tokens, latency; successes per 10,000 tokens.
- **Statistics:** means over requests (each averaged over its seeds), 95% bootstrap CIs; paired bootstrap of differences against the baseline (S0, H0); exact McNemar on per-request majority success.
- **LLM judge** (`eval/judge.py`): llama3.1:8b grades the reviewer note on a 5-question binary rubric for a fixed 20% sample, reasons before verdicts, condition names hidden; length bias reported. The human spot-check file is exported for a team member to label (not done: it needs a person).

## Changes made during development (dev split only)

A 6-request pilot on the dev split showed three design gaps, fixed before any test-split run: (1) the 7B model raised structural issues the rules did not confirm, so in H3/H4 the rules own structural types and the LLM's unconfirmed ones are fed back and dropped; (2) the agent repeated tool calls, so the tool description now suggests a plan and forbids repeats; (3) the compliance checker misused "prompt injection", so its prompt now defines the two issue types it may add. The scorer was also corrected to treat a flagged conflicting value as correct and to count only invented values as hallucinated fields.
