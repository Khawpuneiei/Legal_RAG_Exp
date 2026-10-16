"""Library sync for the Postgres deployment (the Kubernetes counterpart of the Supabase Edge Function's "sync" action):
upsert the approved clause library and graph edges, then embed changed clauses with the TEI gte-small service.

    DATABASE_URL=... EMBED_URL=http://embed:80 python -m src.app.sync
In production the source is the Legal team's approved library in SharePoint (Microsoft Graph); here it is the
versioned files in data/synthetic, so the library hash in every audit event identifies exactly what was used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    import psycopg
    from src.agreement.library import load_library
    lib = load_library()
    ctx = {}
    for line in (ROOT / "data" / "synthetic" / "clause_context.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            ctx[r["clause_id"]] = r["context"]
    embed_url = os.environ["EMBED_URL"].rstrip("/")
    with psycopg.connect(os.environ.get("MIGRATION_DATABASE_URL") or os.environ["DATABASE_URL"], autocommit=True) as conn:
        have = {r[0]: r[1:] for r in conn.execute("select clause_id, version, title, body, context from public.clauses")}
        changed = []
        for c in lib.clauses.values():
            row = (c["version"], c["title"], c["text"], ctx.get(c["clause_id"]))
            if have.get(c["clause_id"]) != row:
                changed.append(c)
        for c in changed:
            text = f"{c['title']}\n{ctx.get(c['clause_id']) or ''}\n{c['text']}"
            r = requests.post(embed_url + "/embed", json={"inputs": text, "normalize": True, "truncate": True}, timeout=60)
            r.raise_for_status()
            vec = "[" + ",".join(f"{x:.6f}" for x in r.json()[0]) + "]"
            conn.execute(
                "insert into public.clauses (clause_id, version, type, title, variant, templates, deviation_cost, alternative_of, body, context, embedding) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::extensions.vector) on conflict (clause_id) do update set version=excluded.version, type=excluded.type, "
                "title=excluded.title, variant=excluded.variant, templates=excluded.templates, deviation_cost=excluded.deviation_cost, "
                "alternative_of=excluded.alternative_of, body=excluded.body, context=excluded.context, embedding=excluded.embedding, updated_at=now()",
                (c["clause_id"], c["version"], c["type"], c["title"], c["variant"], c["templates"], c["deviation_cost"], c["alternative_of"],
                 c["text"], ctx.get(c["clause_id"]), vec))
        with conn.cursor() as cur:
            cur.executemany("insert into public.clause_edges (src, dst, type, weight) values (%s,%s,%s,%s) on conflict do nothing",
                            [(e["src"], e["dst"], e["type"], e["weight"]) for e in lib.edges])
    print(json.dumps(dict(library_sha256=lib.library_sha256, upserted=len(changed), edges=len(lib.edges))))


if __name__ == "__main__":
    main()
