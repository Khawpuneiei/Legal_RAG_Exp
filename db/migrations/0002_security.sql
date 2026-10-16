-- Access control. Clients (the app tier, browser or edge function using the publishable/anon role) can only execute
-- the api_* functions; every table is closed by row level security with no policies, so direct reads and writes are
-- denied. worker_* and audit_append are not exposed to the anon role.
--
-- On plain PostgreSQL (Kubernetes), the roles below are created if missing so the same file applies; the app connects
-- as `app_api` (execute on api_*), the queue worker as `app_worker` (execute on worker_*).

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'app_api') then create role app_api nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'app_worker') then create role app_worker nologin; end if;
end $$;

alter table public.clauses enable row level security;
alter table public.clause_edges enable row level security;
alter table public.requests enable row level security;
alter table public.drafts enable row level security;
alter table public.reviews enable row level security;
alter table public.jobs enable row level security;
alter table public.audit_events enable row level security;

revoke all on all tables in schema public from anon, authenticated, app_api, app_worker;
revoke all on all functions in schema public from public, anon, authenticated;

grant usage on schema public to anon, authenticated, app_api, app_worker;
grant usage on schema extensions to anon, authenticated, app_api, app_worker;

grant execute on function public.api_submit(jsonb) to anon, authenticated, app_api;
grant execute on function public.api_review(jsonb) to anon, authenticated, app_api;
grant execute on function public.api_get_request(uuid) to anon, authenticated, app_api;
grant execute on function public.api_list_requests(text, int) to anon, authenticated, app_api;
grant execute on function public.api_list_audit(int) to anon, authenticated, app_api;
grant execute on function public.api_verify_audit() to anon, authenticated, app_api;
grant execute on function public.api_stats() to anon, authenticated, app_api;
grant execute on function public.hybrid_search(text, extensions.vector, int, text) to anon, authenticated, app_api;
grant execute on function public.worker_claim() to app_worker;
grant execute on function public.worker_complete(jsonb) to app_worker;
