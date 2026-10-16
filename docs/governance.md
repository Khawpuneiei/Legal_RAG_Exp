# AI governance: inventory entry, materiality, controls

Mapped to the MAS Guidelines on Artificial Intelligence Risk Management (issued 7 October 2026; sections 3–4 apply from 7 October 2027, sections 5–6 by 7 October 2028). Prepared for a student prototype on synthetic data: it shows how the system would be documented, not a completed assessment by a control function.

## AI inventory entry (guidelines 4.5–4.8)

| Attribute | Value |
|---|---|
| Use case | Drafting support for standard agreements (NDA, investment management, distribution, side letter, subscription) |
| Business owner | Legal & Compliance (Compliance Senior Associate) |
| Technical owner | Legal technology / the project team |
| Purpose and approved scope | Prepare a first draft and an issue list for a human lawyer. Not for execution, advice or decisions about clients. Singapore entity only |
| AI components | Retrieval models (BGE-M3, bge-reranker-v2-m3, or gte-small), optional LLM (evaluated: qwen2.5:7b local; production candidates: Azure OpenAI via gateway, self-hosted vLLM) |
| Model type | Embedding and cross-encoder retrieval; generative LLM in assist/agent modes only |
| Data | Request form and text (PII-masked), approved template and clause library. Demo: synthetic only |
| Dependencies | Postgres (system of record), embedding service, LLM gateway (optional), Vercel/Supabase (demo) |
| Lifecycle status | Prototype; free-tier demo live; production design ready |
| Materiality (proposed) | Lower: an internal drafting copilot with mandatory human review of every output (guidelines footnotes 12–13). To be confirmed by the designated control function (4.13) |
| Review status | Scoreboard on a frozen test set; independent pre-deployment review pending (5.18) |
| Links | `docs/architecture.md`, `eval/results/`, `configs/policy.yaml`, `skills/legal-agreement-drafting/` |

## Risk materiality reasoning (4.10–4.12)

- **Impact:** a wrong clause or missed issue in a draft could reach a counterparty only if a lawyer approves it; approval is enforced in the database.
- **Complexity:** default mode uses no generative model; LLM modes are bounded (the LLM cannot downgrade a route or own structural checks).
- **Reliance:** the reviewer sees every issue, the clause chosen for every request and its source, and a draft preview; the system is designed to be checked, not trusted.
- **Residual risk:** within appetite for a drafting copilot, provided the controls below operate.

## Controls

| Guideline | Control in this system | Evidence |
|---|---|---|
| 2.5(b) permitted uses, no confidential data in public tools | PII guard before storage and any LLM call; gateway with approved providers only; synthetic data in the demo | `src/app/pii.py`, tests |
| 5.3 data management | Versioned clause library and policy; hashes in every audit event | `src/agreement/library.py` |
| 5.5–5.6 transparency, explainability | Issue list with source (rules or LLM), requirement → clause mapping, retrieval evidence, clause graph dependencies, draft preview | request page |
| 5.9 human oversight | Pre-defined escalation conditions (`configs/policy.yaml`), approval only via `api_review()`, Senior Legal for escalations, decisions logged | SQL functions, integration tests |
| 5.9(d) logs of oversight decisions, near misses | Hash-chained audit events for submissions, drafts, routes and every review decision | `api_verify_audit()` |
| 5.10 third-party AI | Models behind a gateway, replaceable; tested on our own data; compensating controls (rules, human review) | Experiments 1–3 |
| 5.14 evaluation and testing; fn 46 hallucination and prompt injection | Scoreboard with hallucinated-clause rate, defect recall, false alarms, injection resistance, pass^k | `eval/results/` |
| 5.17 reproducibility | Code SHA, policy/library hashes, prompt hash, model id, search backend recorded per draft; experiments re-runnable from caches | `src/drafting/engine.py` |
| 5.18 pre-deployment review | CI release gate; independent review of scoreboard changes before promotion | `.github/workflows/ci.yml` |

## Open items before real use

1. Control-function approval of the materiality rating.
2. Independent validation by someone not on the project team.
3. Human spot-check of the LLM judge (template in `eval/results/judge/human_spotcheck.csv`).
4. Replace synthetic data with the firm's approved library under Legal's change control.
5. Entra ID sign-in in place of the demo role switch.
