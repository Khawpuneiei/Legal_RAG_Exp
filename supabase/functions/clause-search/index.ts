// Clause search + library sync (Supabase Edge Function, Deno).
//
// action "search": embed the query with the built-in gte-small model, then call hybrid_search() (full text + pgvector,
//                  Reciprocal Rank Fusion) as the anon role. Returns clause ids with similarity and RRF score.
// action "sync":   pull the approved library from the app's fixed export URL (never a caller-supplied URL), upsert
//                  changed clauses and graph edges with the service role, then embed up to BATCH clauses that have no
//                  embedding yet. Idempotent: call until "remaining" is 0. In production the source is SharePoint.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const LIBRARY_URL = "https://legal-agreement-ai.vercel.app/seed/library.json";
const TYPES = ["NDA", "IMA", "DIST", "SIDE", "SUBS"];
const BATCH = 6;  // stays under the 2 s CPU limit of a free-tier Edge Function call
const model = new Supabase.ai.Session("gte-small");
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });
}

async function embed(text: string): Promise<number[]> {
  return (await model.run(text, { mean_pool: true, normalize: true })) as number[];
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return json({ error: "invalid JSON" }, 400);
  }
  const action = String(body.action ?? "search");

  if (action === "search") {
    const query = String(body.query ?? "").slice(0, 2000).trim();
    if (!query) return json({ error: "query is required" }, 400);
    const k = Math.min(Math.max(Number(body.k ?? 5) || 5, 1), 20);
    const type = TYPES.includes(String(body.agreement_type)) ? String(body.agreement_type) : null;
    const t0 = Date.now();
    const embedding = await embed(query);
    const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!);
    const { data, error } = await sb.rpc("hybrid_search", {
      query_text: query, query_embedding: JSON.stringify(embedding), match_count: k, agreement_type: type,
    });
    if (error) return json({ error: error.message }, 500);
    return json({ model: "gte-small", ms: Date.now() - t0, results: data });
  }

  if (action === "sync") {
    const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const res = await fetch(LIBRARY_URL, { headers: { accept: "application/json" } });
    if (!res.ok) return json({ error: `library export returned ${res.status}` }, 502);
    const lib = await res.json() as { library_sha256: string; clauses: Record<string, unknown>[]; edges: Record<string, unknown>[] };
    const { data: existing, error: e1 } = await admin.from("clauses").select("clause_id, version, title, body, context");
    if (e1) return json({ error: e1.message }, 500);
    const have = new Map((existing ?? []).map((r) => [r.clause_id, r]));
    const changed = lib.clauses.filter((c) => {
      const h = have.get(c.clause_id as string);
      return !h || h.version !== c.version || h.title !== c.title || h.body !== c.body || h.context !== c.context;
    }).map((c) => ({ ...c, embedding: null, updated_at: new Date().toISOString() }));
    if (changed.length) {
      const { error } = await admin.from("clauses").upsert(changed, { onConflict: "clause_id" });
      if (error) return json({ error: error.message }, 500);
    }
    const { error: e2 } = await admin.from("clause_edges").upsert(lib.edges, { onConflict: "src,dst,type", ignoreDuplicates: true });
    if (e2) return json({ error: e2.message }, 500);
    const { data: todo, error: e3 } = await admin.from("clauses").select("clause_id, title, context, body").is("embedding", null).limit(BATCH);
    if (e3) return json({ error: e3.message }, 500);
    for (const c of todo ?? []) {
      const vec = await embed(`${c.title}\n${c.context ?? ""}\n${c.body}`);
      const { error } = await admin.from("clauses").update({ embedding: JSON.stringify(vec) }).eq("clause_id", c.clause_id);
      if (error) return json({ error: error.message }, 500);
    }
    const { count } = await admin.from("clauses").select("clause_id", { count: "exact", head: true }).is("embedding", null);
    return json({ library_sha256: lib.library_sha256, upserted: changed.length, embedded: (todo ?? []).length, remaining: count ?? null });
  }

  return json({ error: `unknown action ${action}` }, 400);
});
