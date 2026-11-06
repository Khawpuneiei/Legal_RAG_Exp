"""Contextual chunk enrichment for the tax corpus (Experiment 3 R5, Anthropic "Contextual Retrieval").

A local LLM writes one or two sentences situating each chunk; the sentences are prepended to the text that
BM25, the embedder and the reranker see. The tax chunks already carry their hierarchy path and heading
(the teammate's `Chunk.embed_text()`), so the context adds what the path cannot: what the subsection or
paragraph is about within its section or guide.

The whole document does not fit a local 8k context (the Act is 411k tokens, the group relief guide 10k), so
the "document" shown is the chunk's own section (Act; a fixed page of it when the section is long) or the
guide's headings plus the neighbouring paragraphs (guide).

    python -m src.tax.contextual            # all structured chunks; cached, resumable
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import sys

from tqdm import tqdm

from src.common import CACHE
from src.llm.ollama import OllamaLLM
from src.retrieval.contextual import CHUNK_PROMPT
from src.tax.corpus import chunks

MODEL = "qwen2.5:7b"
MAX_DOC_CHARS = 12000
PAGE_OVERLAP = 3500        # longer than any chunk, so a chunk starting on a page ends on it
NEIGHBOURS = 3
OUT = CACHE / "tax" / f"contexts-{MODEL.replace(':', '_')}.jsonl"   # derived from IRAS text: never committed


def documents() -> dict[str, str]:
    """chunk_id -> the 'document' shown to the LLM for that chunk."""
    rows = chunks("structured")
    by_section: dict[str, list] = {}
    by_guide: dict[str, list] = {}
    for c in rows:
        if c.doc_type == "act":
            by_section.setdefault(c.section, []).append(c)
        else:
            by_guide.setdefault(c.chunk_id.split(":", 1)[0], []).append(c)
    out = {}
    for sec, group in by_section.items():
        head = group[0].path.split(" > ")
        title = f"{head[0]}, {head[1] if len(head) > 1 else ''}, section {sec} ({group[0].heading})"
        pieces = [f"({c.subsection}) {c.text}" if c.subsection else c.text for c in group]
        body = "\n".join(pieces)
        offset = 0
        for c, piece in zip(group, pieces):
            # A long section is cut into fixed pages (with overlap, so every chunk fits in its page). Chunks on
            # the same page share the prompt prefix, which lets Ollama reuse its KV cache: 2-3x faster.
            page = offset // MAX_DOC_CHARS
            doc = body if len(body) <= MAX_DOC_CHARS + PAGE_OVERLAP else body[page * MAX_DOC_CHARS:(page + 1) * MAX_DOC_CHARS + PAGE_OVERLAP]
            out[c.chunk_id] = f"{title}\n\n{doc}"
            offset += len(piece) + 1
    for group in by_guide.values():
        headings = list(dict.fromkeys(c.heading for c in group if c.heading))
        title = f"IRAS {group[0].doc_title}. Headings: " + "; ".join(headings)
        for i, c in enumerate(group):
            near = group[max(0, i - NEIGHBOURS): i + NEIGHBOURS + 1]
            body = "\n\n".join(f"{n.para} {n.text}" for n in near)[:MAX_DOC_CHARS]
            out[c.chunk_id] = f"{title}\n\n{body}"
    return out


def contexts(workers: int = 4) -> dict[str, str]:
    """chunk_id -> LLM context sentence(s). Reads the cache file; generates what is missing."""
    done: dict[str, str] = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["chunk_id"]] = rec["context"]
    todo = [c for c in chunks("structured") if c.chunk_id not in done]
    if not todo:
        return done
    llm = OllamaLLM(MODEL, num_ctx=8192, cache_name="tax-context")
    docs = documents()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    def one(c):
        text = llm.generate(CHUNK_PROMPT.format(doc=docs[c.chunk_id], chunk=c.text), max_tokens=120)["text"].strip()
        return c.chunk_id, " ".join(text.split())

    with open(OUT, "a", encoding="utf-8") as f, cf.ThreadPoolExecutor(workers) as ex:
        for cid, ctx in tqdm(ex.map(one, todo), total=len(todo), desc="tax chunk context", file=sys.stdout, mininterval=30):
            done[cid] = ctx
            f.write(json.dumps({"chunk_id": cid, "context": ctx}, ensure_ascii=False) + "\n")
            f.flush()
    return done


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    n = len(contexts(int(os.environ.get("TAX_CONTEXT_WORKERS", "4"))))
    print(f"{n} contexts in {OUT}")
