# Runbook

## Health

| Check | Healthy |
|---|---|
| `GET /healthz` | `{"status":"ok"}` (process up) |
| `GET /readyz` | `200`, `store` and `search` true. `503` means a dependency is down; the pod leaves the load balancer |
| `GET /api/v1/version` | code SHA, drafting mode, store, search backend, policy and library hashes |
| `GET /api/v1/audit/verify` | `{"intact": true}` |

## Common incidents

**Requests stuck in QUEUED (queue mode).** Workers are down or failing. Check worker logs for `job_failed` and `worker_retry` (database unreachable or not migrated: the worker backs off up to 30 s and keeps its heartbeat, it does not crash-loop); a job is retried 3 times and a lock older than 5 minutes is reclaimed. Scale workers: `kubectl -n legal-ai scale deploy/legal-legal-ai-worker --replicas=4`.

**`/readyz` reports search false.** Free tier: the Supabase project may be paused after a week of inactivity (resume it in the dashboard) or the Edge Function failed (check its logs). Kubernetes: TEI pods not ready (first start downloads the model).

**Search returns nothing relevant after a library change.** Embeddings are missing: run the sync (Edge Function `sync` action until `remaining` is 0, or `kubectl create job --from=cronjob/legal-legal-ai-library-sync sync-now`).

**Audit chain reported broken.** Treat as a security incident: freeze reviews (scale the API to 0 or set the ingress to maintenance), compare with the latest WORM export, and identify the first broken event id returned by `api_verify_audit()`.

**LLM endpoint down (assist/agent mode).** Set `DRAFTING_MODE=rules` and roll the API and workers; drafting continues without a model. Re-enable after the gateway recovers.

**A policy, prompt, model or library change.** Run the scoreboard (`scripts/run_all_experiments.sh` for LLM modes, `eval/deployed_eval.py` for the deployed profile) and the release gate tests before promoting. Record the new hashes; they appear in every subsequent audit event.

## Verifying the Helm chart locally

```bash
helm lint deploy/helm/legal-agreement-ai
```
```bash
helm template demo deploy/helm/legal-agreement-ai | kubeconform -strict -summary -kubernetes-version 1.30.0
```

With Docker running, a full install on kind:

```bash
kind create cluster --name legal
```
```bash
docker build -f deploy/docker/Dockerfile -t legal-agreement-ai:local . && kind load docker-image legal-agreement-ai:local --name legal
```
```bash
kubectl create namespace legal-ai && kubectl -n legal-ai create secret generic legal-agreement-ai-secrets --from-env-file=deploy/kind-secrets.env
```
```bash
helm upgrade --install legal deploy/helm/legal-agreement-ai -n legal-ai -f deploy/helm/legal-agreement-ai/values-kind.yaml --timeout 20m
```
```bash
kubectl -n legal-ai wait --for=condition=Ready pod -l app.kubernetes.io/component=api --timeout=300s
```

Do not use `--wait` with the in-cluster development database: its migrations run as a post-install hook, which Helm only starts after `--wait` is satisfied, and the API is not ready before the schema exists. With a managed database the migrations run pre-install, so `--wait` is fine.
```bash
kubectl -n legal-ai port-forward svc/legal-legal-ai-api 8000:80
```

`deploy/kind-secrets.env` (not committed) contains `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`, `WORKER_DB_PASSWORD`, and the three URLs pointing at `legal-legal-ai-pg:5432/legal`.
