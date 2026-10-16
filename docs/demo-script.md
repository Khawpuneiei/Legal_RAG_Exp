# Demo script (5 minutes)

Live: **https://legal-agreement-ai.vercel.app** (free tier: Vercel + Supabase, Singapore region). Open it a minute before presenting: the first request after a quiet period wakes the serverless function (about 3 seconds).

| Time | Do | Say |
|---|---|---|
| 0:00 | Dashboard | The problem: staff ask Legal for standard agreements by email, often incomplete; Legal re-keys them. The system drafts from approved templates and clauses, checks the request, and routes it, but never executes anything without a lawyer. The flow strip shows which steps are code (grey), model-assisted (blue) and human (orange). |
| 0:30 | **Try it → Clean NDA**, submit | One click produces a routed draft in about a second: fields, each special request matched to an approved clause, the clause-graph dependencies it pulled in (definitions, legally required clauses), a .docx download. Route: Legal review. |
| 1:15 | **Prompt injection in the request**, submit | The request text tells "the AI" to skip review. The text is treated as data: the rule detector flags it and the policy escalates to Senior Legal. An LLM in the loop could add issues but never lower the route. |
| 1:45 | Switch role to **Legal reviewer**, try **Approve** | Refused: escalated drafts need Senior Legal. This is enforced inside the database function, not in the page. Switch to **Senior Legal / Compliance**, approve. |
| 2:15 | **Audit trail** | Append-only, hash-chained; the page re-verifies the chain. Every draft event records the policy, library and code versions (MAS AI RM 5.9, 5.17). |
| 2:45 | **Missing required field** or **Date conflict** | Data problems go back to the requester instead of reaching a lawyer: the back-and-forth the internship description wants removed. |
| 3:15 | **Scoreboard** | The three experiments on the same frozen test set: skill files (RQ1), agent harnesses (RQ2), retrieval (RQ3). Point to what did not win, too. |
| 4:00 | **Architecture** | Same code, three targets: this free demo, Docker Compose, and Kubernetes on Azure (Helm chart, Terraform, CI with SQL integration tests). Decisions and their evidence are in `docs/architecture.md`. |
| 4:30 | Close | Limitations: synthetic data, a 7B local model, the free tier's lighter search (its measured scores are in `eval/results/deployed/`). |

## If you want LLM modes in the demo

The cloud demo runs in rules mode (no model cost). To show the agent harness live, run the production-like stack locally with your GPU:

```bash
cp deploy/.env.example deploy/.env
```

Set `OLLAMA_HOST=http://host.docker.internal:11434` and `DRAFTING_MODE=agent` in `deploy/.env`, then:

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
```

Open http://localhost:8000. Agent mode takes about a minute per draft with qwen2.5:7b on an 8 GB laptop GPU; the queue workers process it in the background and the request page shows the result when it is ready.

## Backup plan

If the venue network blocks the site: `uvicorn src.app.main:app` runs the whole app locally in memory (`STORE=memory`, `SEARCH=keyword`), no database or internet needed.
