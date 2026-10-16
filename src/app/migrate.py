"""Apply db/migrations/*.sql in order, once each, recording them in schema_migrations (Kubernetes pre-upgrade Job).

    DATABASE_URL=postgresql://... python -m src.app.migrate
Runs inside one advisory lock so two pods can never migrate concurrently. Each file runs in its own transaction.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


def main() -> None:
    import psycopg
    dsn = os.environ.get("MIGRATION_DATABASE_URL") or os.environ["DATABASE_URL"]
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("select pg_advisory_lock(424242)")
        conn.execute("create table if not exists public.schema_migrations (name text primary key, sha256 text not null, applied_at timestamptz not null default now())")
        done = {r[0]: r[1] for r in conn.execute("select name, sha256 from public.schema_migrations")}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            sql = f.read_text(encoding="utf-8")
            digest = hashlib.sha256(sql.encode()).hexdigest()
            if f.name in done:
                if done[f.name] != digest:
                    print(f"WARNING {f.name} changed after it was applied; write a new migration instead", file=sys.stderr)
                continue
            with conn.transaction():
                conn.execute(sql)
                conn.execute("insert into public.schema_migrations (name, sha256) values (%s, %s)", (f.name, digest))
            print(f"applied {f.name}")
        conn.execute("select pg_advisory_unlock(424242)")
    print("migrations up to date")


if __name__ == "__main__":
    main()
