-- Legal Agreement AI: core schema (portable: Supabase Postgres 17 and plain PostgreSQL 16+ with pgvector).
--
-- Design (docs/architecture.md):
--  * The database is the system of record and the workflow state machine. Every state change happens inside one
--    SQL function, in one transaction, together with its audit event, so the app tier stays stateless
--    (serverless-safe) and a crash can never leave a request half-updated.
--  * audit_events is append-only (UPDATE/DELETE raise) and hash-chained (each row stores sha256(prev_hash || row)),
--    so tampering is detectable (MAS AI RM Guidelines 5.9(d), 5.17).
--  * Clients never touch tables directly: they call the api_* functions. Clause search is hybrid
--    (full-text tsvector + pgvector) fused with Reciprocal Rank Fusion inside hybrid_search().

create schema if not exists extensions;
create extension if not exists vector with schema extensions;

-- ------------------------------------------------------------------------------------------------ clause library
create table if not exists public.clauses (
  clause_id      text primary key,
  version        text not null,
  type           text not null,
  title          text not null,
  variant        text not null check (variant in ('definition', 'standard', 'fallback', 'optional')),
  templates      text[] not null,
  deviation_cost real not null default 0,
  alternative_of text,
  body           text not null,
  context        text,                          -- contextual-retrieval prefix (Experiment 3, R5)
  fts            tsvector generated always as (
                   setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                   setweight(to_tsvector('english', coalesce(context, '')), 'B') ||
                   setweight(to_tsvector('english', body), 'B')) stored,
  embedding      extensions.vector(384),        -- gte-small, normalised
  approved_by    text not null default 'Legal (synthetic library)',
  updated_at     timestamptz not null default now()
);
create index if not exists clauses_fts_idx on public.clauses using gin (fts);
create index if not exists clauses_embedding_idx on public.clauses using hnsw (embedding extensions.vector_ip_ops);

create table if not exists public.clause_edges (
  src    text not null,
  dst    text not null,
  type   text not null check (type in ('CONTAINS', 'DEFINED_IN', 'REFERS_TO', 'REQUIRES', 'ALTERNATIVE_OF')),
  weight real not null default 0,
  primary key (src, dst, type)
);

-- ------------------------------------------------------------------------------------------------ workflow
create table if not exists public.requests (
  id             uuid primary key default gen_random_uuid(),
  ref            text unique not null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  requester      text not null,
  agreement_type text not null check (agreement_type in ('NDA', 'IMA', 'DIST', 'SIDE', 'SUBS')),
  form           jsonb not null,
  text_masked    text not null check (length(text_masked) <= 6000),
  pii_findings   jsonb not null default '{}'::jsonb,
  status         text not null check (status in ('QUEUED', 'IN_REVIEW', 'ESCALATED', 'RETURNED', 'APPROVED', 'REJECTED', 'FAILED')),
  route          text check (route in ('standard_review', 'escalate', 'return_to_requester')),
  draft_version  int not null default 0
);
create index if not exists requests_status_idx on public.requests (status, created_at desc);

create table if not exists public.drafts (
  id            bigint generated always as identity primary key,
  request_id    uuid not null references public.requests (id),
  version       int not null,
  created_at    timestamptz not null default now(),
  mode          text not null,                  -- rules | assist | agent (drafting configuration)
  config        jsonb not null,                 -- policy/library sha256, model, retrieval backend, tau, code version
  fields        jsonb not null,
  selections    jsonb not null,
  issues        jsonb not null,
  route         text not null check (route in ('standard_review', 'escalate', 'return_to_requester')),
  evidence      jsonb not null default '{}'::jsonb,
  reviewer_note text,
  unique (request_id, version)
);

create table if not exists public.reviews (
  id            bigint generated always as identity primary key,
  request_id    uuid not null references public.requests (id),
  draft_version int not null,
  created_at    timestamptz not null default now(),
  reviewer      text not null,
  reviewer_role text not null,
  decision      text not null check (decision in ('approve', 'reject', 'request_changes', 'escalate')),
  comment       text check (length(comment) <= 2000)
);

create table if not exists public.jobs (            -- work queue for asynchronous drafting (production "queue" mode)
  id          bigint generated always as identity primary key,
  request_id  uuid not null references public.requests (id),
  created_at  timestamptz not null default now(),
  attempts    int not null default 0,
  locked_at   timestamptz,
  done_at     timestamptz,
  last_error  text
);
create index if not exists jobs_pending_idx on public.jobs (created_at) where done_at is null;

-- ------------------------------------------------------------------------------------------------ audit trail
create table if not exists public.audit_events (
  id          bigint generated always as identity primary key,
  at          timestamptz not null default now(),
  request_id  uuid references public.requests (id),
  actor       text not null,
  actor_role  text not null,
  event       text not null,
  details     jsonb not null default '{}'::jsonb,
  prev_hash   text,
  hash        text not null
);
create index if not exists audit_request_idx on public.audit_events (request_id, id);

create or replace function public.forbid_change() returns trigger
language plpgsql set search_path = '' as $$
begin
  raise exception 'audit_events is append-only';
end $$;

drop trigger if exists audit_append_only on public.audit_events;
create trigger audit_append_only before update or delete on public.audit_events
  for each row execute function public.forbid_change();

-- Internal: append one hash-chained audit event (serialised with an advisory lock so the chain is linear).
create or replace function public.audit_append(p_request uuid, p_actor text, p_role text, p_event text, p_details jsonb)
returns text language plpgsql set search_path = '' as $$
declare
  v_prev text;
  v_hash text;
  v_at timestamptz := clock_timestamp();
begin
  perform pg_advisory_xact_lock(7311);
  select hash into v_prev from public.audit_events order by id desc limit 1;
  v_hash := encode(sha256(convert_to(coalesce(v_prev, '') || '|' || v_at::text || '|' || coalesce(p_request::text, '') || '|' ||
                                     p_actor || '|' || p_role || '|' || p_event || '|' || coalesce(p_details, '{}'::jsonb)::text, 'UTF8')), 'hex');
  insert into public.audit_events (at, request_id, actor, actor_role, event, details, prev_hash, hash)
  values (v_at, p_request, p_actor, p_role, p_event, coalesce(p_details, '{}'::jsonb), v_prev, v_hash);
  return v_hash;
end $$;

-- ------------------------------------------------------------------------------------------------ api functions
-- Submit a request. If p.draft is present (inline mode) the draft is stored and routed in the same transaction;
-- otherwise the request is QUEUED and a job is created for a worker (queue mode).
create or replace function public.api_submit(p jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_id uuid;
  v_ref text;
  v_route text := p -> 'draft' ->> 'route';
  v_status text;
  v_recent int;
  v_role text := coalesce(p ->> 'role', 'requester');
begin
  if coalesce(p ->> 'requester', '') = '' or coalesce(p ->> 'agreement_type', '') = '' then
    raise exception 'requester and agreement_type are required';
  end if;
  if length(coalesce(p ->> 'text_masked', '')) > 6000 or pg_column_size(p) > 200000 then
    raise exception 'request too large';
  end if;
  select count(*) into v_recent from public.requests where created_at > now() - interval '1 hour';
  if v_recent >= 300 then
    raise exception 'rate limit: too many requests this hour';
  end if;
  v_ref := 'REQ-' || to_char(now() at time zone 'Asia/Singapore', 'YYMMDD') || '-' || upper(substr(md5(gen_random_uuid()::text), 1, 5));
  v_status := case when p ? 'draft' then case v_route when 'escalate' then 'ESCALATED' when 'return_to_requester' then 'RETURNED' else 'IN_REVIEW' end
                   else 'QUEUED' end;
  insert into public.requests (ref, requester, agreement_type, form, text_masked, pii_findings, status, route, draft_version)
  values (v_ref, p ->> 'requester', p ->> 'agreement_type', coalesce(p -> 'form', '{}'::jsonb), coalesce(p ->> 'text_masked', ''),
          coalesce(p -> 'pii_findings', '{}'::jsonb), v_status, v_route, case when p ? 'draft' then 1 else 0 end)
  returning id into v_id;
  perform public.audit_append(v_id, p ->> 'requester', v_role, 'request_submitted',
          jsonb_build_object('ref', v_ref, 'agreement_type', p ->> 'agreement_type', 'pii_findings', coalesce(p -> 'pii_findings', '{}'::jsonb)));
  if p ? 'draft' then
    perform public.store_draft(v_id, 1, p -> 'draft');
  else
    insert into public.jobs (request_id) values (v_id);
    perform public.audit_append(v_id, 'system', 'workflow', 'queued_for_drafting', '{}'::jsonb);
  end if;
  return jsonb_build_object('id', v_id, 'ref', v_ref, 'status', v_status, 'route', v_route);
end $$;

create or replace function public.store_draft(p_request uuid, p_version int, d jsonb) returns void
language plpgsql set search_path = '' as $$
declare
  v_route text := d ->> 'route';
begin
  insert into public.drafts (request_id, version, mode, config, fields, selections, issues, route, evidence, reviewer_note)
  values (p_request, p_version, coalesce(d ->> 'mode', 'rules'), coalesce(d -> 'config', '{}'::jsonb), coalesce(d -> 'fields', '{}'::jsonb),
          coalesce(d -> 'selections', '[]'::jsonb), coalesce(d -> 'issues', '[]'::jsonb), v_route, coalesce(d -> 'evidence', '{}'::jsonb), d ->> 'reviewer_note');
  perform public.audit_append(p_request, 'drafting-engine', 'system', 'draft_generated',
          jsonb_build_object('version', p_version, 'mode', d ->> 'mode', 'config', d -> 'config',
                             'clauses', (select coalesce(jsonb_agg(s -> 'clause_id'), '[]'::jsonb) from jsonb_array_elements(coalesce(d -> 'selections', '[]'::jsonb)) s),
                             'issues', (select coalesce(jsonb_agg(i -> 'type'), '[]'::jsonb) from jsonb_array_elements(coalesce(d -> 'issues', '[]'::jsonb)) i)));
  perform public.audit_append(p_request, 'routing-policy', 'system', 'routed', jsonb_build_object('route', v_route));
end $$;

-- Worker side of queue mode: claim one job (SKIP LOCKED) and complete it.
create or replace function public.worker_claim() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_job record;
begin
  select j.* into v_job from public.jobs j
  where j.done_at is null and (j.locked_at is null or j.locked_at < now() - interval '5 minutes') and j.attempts < 3
  order by j.created_at for update skip locked limit 1;
  if not found then
    return null;
  end if;
  update public.jobs set locked_at = now(), attempts = attempts + 1 where id = v_job.id;
  return (select jsonb_build_object('job_id', v_job.id, 'request_id', r.id, 'agreement_type', r.agreement_type, 'form', r.form, 'text', r.text_masked)
          from public.requests r where r.id = v_job.request_id);
end $$;

create or replace function public.worker_complete(p jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_req uuid := (p ->> 'request_id')::uuid;
  v_route text := p -> 'draft' ->> 'route';
begin
  if p ? 'error' then
    update public.jobs set last_error = p ->> 'error', locked_at = null where id = (p ->> 'job_id')::bigint;
    perform public.audit_append(v_req, 'drafting-engine', 'system', 'draft_failed', jsonb_build_object('error', left(p ->> 'error', 500)));
    return jsonb_build_object('ok', false);
  end if;
  perform public.store_draft(v_req, 1, p -> 'draft');
  update public.requests set status = case v_route when 'escalate' then 'ESCALATED' when 'return_to_requester' then 'RETURNED' else 'IN_REVIEW' end,
                             route = v_route, draft_version = 1, updated_at = now()
  where id = v_req and status = 'QUEUED';
  update public.jobs set done_at = now() where id = (p ->> 'job_id')::bigint;
  return jsonb_build_object('ok', true);
end $$;

-- Human review: the only way a draft reaches APPROVED. Escalated drafts need senior_legal.
create or replace function public.api_review(p jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_req public.requests%rowtype;
  v_decision text := p ->> 'decision';
  v_role text := p ->> 'role';
  v_new text;
begin
  select * into v_req from public.requests where id = (p ->> 'request_id')::uuid for update;
  if not found then
    raise exception 'request not found';
  end if;
  if v_role not in ('legal_reviewer', 'senior_legal') then
    raise exception 'only Legal can review drafts';
  end if;
  if v_req.status not in ('IN_REVIEW', 'ESCALATED') then
    raise exception 'request is % and cannot be reviewed', v_req.status;
  end if;
  if v_decision = 'approve' and v_req.status = 'ESCALATED' and v_role <> 'senior_legal' then
    raise exception 'escalated drafts must be approved by Senior Legal / Compliance';
  end if;
  v_new := case v_decision when 'approve' then 'APPROVED' when 'reject' then 'REJECTED' when 'request_changes' then 'RETURNED'
                           when 'escalate' then 'ESCALATED' else null end;
  if v_new is null then
    raise exception 'unknown decision %', v_decision;
  end if;
  insert into public.reviews (request_id, draft_version, reviewer, reviewer_role, decision, comment)
  values (v_req.id, v_req.draft_version, coalesce(p ->> 'reviewer', 'unknown'), v_role, v_decision, left(p ->> 'comment', 2000));
  update public.requests set status = v_new, route = case when v_decision = 'escalate' then 'escalate' else route end, updated_at = now() where id = v_req.id;
  perform public.audit_append(v_req.id, coalesce(p ->> 'reviewer', 'unknown'), v_role, 'review_' || v_decision,
          jsonb_build_object('draft_version', v_req.draft_version, 'comment', left(p ->> 'comment', 300), 'from', v_req.status, 'to', v_new));
  return jsonb_build_object('id', v_req.id, 'status', v_new);
end $$;

create or replace function public.api_get_request(p_id uuid) returns jsonb
language sql security definer set search_path = '' stable as $$
  select jsonb_build_object(
    'request', to_jsonb(r),
    'draft', (select to_jsonb(d) from public.drafts d where d.request_id = r.id order by version desc limit 1),
    'reviews', (select coalesce(jsonb_agg(to_jsonb(v) order by v.id), '[]'::jsonb) from public.reviews v where v.request_id = r.id),
    'audit', (select coalesce(jsonb_agg(jsonb_build_object('id', a.id, 'at', a.at, 'actor', a.actor, 'actor_role', a.actor_role, 'event', a.event,
                                                           'details', a.details, 'hash', a.hash, 'prev_hash', a.prev_hash) order by a.id), '[]'::jsonb)
              from public.audit_events a where a.request_id = r.id))
  from public.requests r where r.id = p_id;
$$;

create or replace function public.api_list_requests(p_status text default null, p_limit int default 50) returns jsonb
language sql security definer set search_path = '' stable as $$
  select coalesce(jsonb_agg(x order by x.created_at desc), '[]'::jsonb) from (
    select r.id, r.ref, r.created_at, r.requester, r.agreement_type, r.status, r.route, r.form ->> 'counterparty_name' as counterparty,
           (select jsonb_array_length(d.issues) from public.drafts d where d.request_id = r.id order by version desc limit 1) as n_issues
    from public.requests r where p_status is null or r.status = p_status
    order by r.created_at desc limit least(greatest(p_limit, 1), 200)) x;
$$;

create or replace function public.api_list_audit(p_limit int default 100) returns jsonb
language sql security definer set search_path = '' stable as $$
  select coalesce(jsonb_agg(x order by x.id desc), '[]'::jsonb) from (
    select a.id, a.at, a.request_id, (select ref from public.requests r where r.id = a.request_id) as ref, a.actor, a.actor_role, a.event, a.hash, a.prev_hash
    from public.audit_events a order by a.id desc limit least(greatest(p_limit, 1), 500)) x;
$$;

-- Recompute the hash chain and report the first broken link (null if intact).
create or replace function public.api_verify_audit() returns jsonb
language plpgsql security definer set search_path = '' stable as $$
declare
  r record;
  v_prev text := null;
  v_calc text;
  v_n int := 0;
begin
  for r in select * from public.audit_events order by id loop
    v_calc := encode(sha256(convert_to(coalesce(v_prev, '') || '|' || r.at::text || '|' || coalesce(r.request_id::text, '') || '|' ||
                                       r.actor || '|' || r.actor_role || '|' || r.event || '|' || r.details::text, 'UTF8')), 'hex');
    if v_calc <> r.hash or coalesce(r.prev_hash, '') <> coalesce(v_prev, '') then
      return jsonb_build_object('intact', false, 'broken_at', r.id, 'checked', v_n);
    end if;
    v_prev := r.hash;
    v_n := v_n + 1;
  end loop;
  return jsonb_build_object('intact', true, 'checked', v_n);
end $$;

create or replace function public.api_stats() returns jsonb
language sql security definer set search_path = '' stable as $$
  select jsonb_build_object(
    'by_status', (select coalesce(jsonb_object_agg(status, n), '{}'::jsonb) from (select status, count(*) n from public.requests group by status) s),
    'by_route', (select coalesce(jsonb_object_agg(coalesce(route, 'none'), n), '{}'::jsonb) from (select route, count(*) n from public.requests group by route) s),
    'requests', (select count(*) from public.requests),
    'audit_events', (select count(*) from public.audit_events),
    'clauses', (select count(*) from public.clauses),
    'clauses_indexed', (select count(*) from public.clauses where embedding is not null));
$$;

-- Hybrid clause search: full text + vector similarity, fused with Reciprocal Rank Fusion (k = 50).
create or replace function public.hybrid_search(query_text text, query_embedding extensions.vector(384), match_count int default 8,
                                                agreement_type text default null)
returns table (clause_id text, title text, variant text, deviation_cost real, similarity real, rrf_score real)
language sql security definer set search_path = '' stable as $$
  with eligible as (
    select c.* from public.clauses c
    where agreement_type is null or agreement_type = any (c.templates) or 'ALL' = any (c.templates)
  ),
  full_text as (
    select e.clause_id, row_number() over (order by ts_rank_cd(e.fts, websearch_to_tsquery('english', query_text)) desc) as rank_ix
    from eligible e where e.fts @@ websearch_to_tsquery('english', query_text)
    order by rank_ix limit 60
  ),
  full_text_or as (   -- websearch_to_tsquery ANDs terms; an OR query keeps long requests from matching nothing
    select e.clause_id, row_number() over (order by ts_rank_cd(e.fts, q) desc) as rank_ix
    from eligible e, (select to_tsquery('english', string_agg(quote_literal(lexeme), ' | ')) as q
                      from unnest(to_tsvector('english', query_text)) u) qq
    where qq.q is not null and e.fts @@ qq.q
    order by rank_ix limit 60
  ),
  semantic as (
    select e.clause_id, row_number() over (order by e.embedding operator(extensions.<#>) query_embedding) as rank_ix,
           -(e.embedding operator(extensions.<#>) query_embedding) as sim
    from eligible e where e.embedding is not null
    order by rank_ix limit 60
  ),
  fused as (
    select coalesce(s.clause_id, f.clause_id, o.clause_id) as clause_id,
           coalesce(1.0 / (50 + f.rank_ix), 0) + coalesce(1.0 / (50 + o.rank_ix), 0) + coalesce(1.0 / (50 + s.rank_ix), 0) as rrf,
           s.sim
    from semantic s
    full outer join full_text f on f.clause_id = s.clause_id
    full outer join full_text_or o on o.clause_id = coalesce(s.clause_id, f.clause_id)
  )
  select c.clause_id, c.title, c.variant, c.deviation_cost, coalesce(fu.sim, 0)::real, fu.rrf::real
  from fused fu join public.clauses c on c.clause_id = fu.clause_id
  order by fu.rrf desc
  limit least(greatest(match_count, 1), 50);
$$;
