"""Doctrinal query rewrite (condition R4q).

Motivated by SG-LegalCite (principle-augmented queries) and the Stanford Bar Exam QA work
(structured legal-reasoning query expansion): before retrieval, an LLM restates the request as the
clause types and legal purposes a lawyer would look up. The rewrite is appended to, not substituted
for, the original query.
"""
from __future__ import annotations

from tqdm import tqdm

from src.llm.ollama import OllamaLLM

SYSTEM = "You are a legal research assistant at a Singapore fund management company."
PROMPT = """A colleague sent this request:
<request>
{query}
</request>
List the contract clause(s) that a lawyer would need to find in an approved clause library to satisfy this request. For each need, write one short line naming the clause type and its legal purpose in formal legal language (for example: "Non-solicitation of employees - prohibits poaching staff for a fixed period"). Do not add needs that are not in the request. Output only the lines."""


def rewrite_queries(queries: list[str], llm: OllamaLLM) -> list[str]:
    out = []
    for q in tqdm(queries, desc="query rewrite", disable=len(queries) < 50):
        r = llm.generate(PROMPT.format(query=q), system=SYSTEM, max_tokens=160)["text"].strip()
        out.append(f"{q}\nLegal purpose: {r}")
    return out
