# Deployment guide

Three targets share one codebase and one set of migrations (see `docs/architecture.md`, section 4).

## A. Free demo: Vercel + Supabase (live)

**URL:** https://legal-agreement-ai.vercel.app

| Piece | Where | How it was set up |
|---|---|---|
| Database | Supabase project `legal-agreement-ai`, region `ap-southeast-1` (Singapore), free plan | `db/migrations/0001_core.sql`, `0002_security.sql`, `0003_login_grants.sql` |
| Clause search | Edge Function `clause-search` (gte-small + `hybrid_search()`) | `supabase/functions/clause-search/index.ts` |
| Library index | Edge Function action `sync` pulls `/seed/library.json` from the app and embeds clauses in batches | see below |
| App | Vercel project `legal-agreement-ai`, region `sin1`, Hobby plan | `index.py`, `vercel.json`, `configs/deployments/vercel.env` |
| Delivery | GitHub repository connected to Vercel: pull requests get preview deployments, `main` deploys to production | `.github/workflows/ci.yml` runs the checks |

The app needs no secrets. `configs/deployments/vercel.env` holds the Supabase URL and the publishable keys, which are public by design: they can only execute the `api_*` functions.

Re-index the clause library after it changes (repeat until `remaining` is 0):

```bash
curl -s -X POST "https://uwqfgzonlcbpzmcaucsu.supabase.co/functions/v1/clause-search" -H "Authorization: Bearer $SUPABASE_ANON_JWT" -H "Content-Type: application/json" -d '{"action":"sync"}'
```

Re-score the deployed configuration on the frozen test split:

```bash
python eval/deployed_eval.py
```

Optional LLM for the demo (assist mode): set `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` in the Vercel project's environment variables (any OpenAI-compatible endpoint), then redeploy. Without them the demo runs in rules mode.

Free-tier limits to know: Supabase pauses a free project after a week without activity (open the dashboard to resume it); Vercel Hobby functions run up to 300 s; Supabase Edge Functions have a 2 s CPU limit per call, which is why the sync embeds in small batches.

## B. Single machine: Docker Compose

```bash
cp deploy/.env.example deploy/.env
```
```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
```

Starts Postgres + pgvector, runs migrations, starts TEI (gte-small), syncs the library, then the API on http://localhost:8000 and two queue workers. To use the host's Ollama for assist/agent mode, set `OLLAMA_HOST=http://host.docker.internal:11434` in `deploy/.env`.

## C. Production: Kubernetes (Helm)

Prerequisites: a cluster with an ingress controller, a managed PostgreSQL 16+ with the `vector` extension allowed, a registry, and a Secret (normally synced from Key Vault by External Secrets) named `legal-agreement-ai-secrets` with:

| Key | Value |
|---|---|
| `DATABASE_URL` | `postgresql://app_login:...@host:5432/legal?sslmode=require` |
| `WORKER_DATABASE_URL` | `postgresql://worker_login:...@host:5432/legal?sslmode=require` |
| `MIGRATION_DATABASE_URL` | owner role, used only by the migration and sync jobs |
| `LLM_API_KEY` | optional, for the LLM gateway |

```bash
docker build -f deploy/docker/Dockerfile --build-arg GIT_SHA=$(git rev-parse --short HEAD) -t <registry>/legal-agreement-ai:$(git rev-parse --short HEAD) .
```
```bash
helm upgrade --install legal deploy/helm/legal-agreement-ai -n legal-ai --create-namespace --set image.repository=<registry>/legal-agreement-ai --set image.tag=$(git rev-parse --short HEAD) --set ingress.host=legal-ai.<your-domain>
```

The chart runs migrations before each install/upgrade (Helm hook Job), syncs the library after each release and hourly (CronJob), and deploys the API, workers and TEI with probes, autoscaling, a disruption budget and default-deny network policies.

Local Kubernetes check (kind): `deploy/helm/legal-agreement-ai/values-kind.yaml` enables an in-cluster development Postgres and turns off the ingress; see `docs/runbook.md` for the exact commands used to verify the chart.
