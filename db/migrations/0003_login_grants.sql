-- Login roles are created by the platform with credentials from the secret store (Terraform / Key Vault, or the
-- local docker-compose init script); this migration only grants them the group roles, if they exist.
--   app_login    -> app_api    (EXECUTE on api_* and hybrid_search)
--   worker_login -> app_worker (EXECUTE on worker_*)
-- No-op on Supabase, where the API roles are anon/authenticated.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'app_login') then
    execute 'grant app_api to app_login';
  end if;
  if exists (select 1 from pg_roles where rolname = 'worker_login') then
    execute 'grant app_worker to worker_login';
    execute 'grant app_api to worker_login';
  end if;
end $$;
