"""Download the public benchmarks used in Experiment 3 into data/public/ (git-ignored).

* ACORD (Wang et al., ACL 2025), official release on Hugging Face, CC BY 4.0:
  https://huggingface.co/datasets/theatticusproject/acord
* LegalBench-RAG (Pipitone & Houir Alami, 2024). The official data link is a Dropbox folder
  (https://github.com/zeroentropy-ai/legalbenchrag) that cannot be fetched non-interactively, so we
  use the byte-exact Hugging Face copy awinml/legalbench-rag, verify every file against its
  SHA256SUMS, and then rebuild LegalBench-RAG-mini with the official sampling rule
  (legalbenchrag/benchmark.py: 194 tests per dataset, ordered by random.seed(file_path)).
  The rebuild is accepted only if it reproduces the paper's Table 3: 776 queries, 72 documents,
  8,682,104 characters.

Usage:  python scripts/download_public.py
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import urllib.parse
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data" / "public"
HF = "https://huggingface.co"

ACORD_ZIP = f"{HF}/datasets/theatticusproject/acord/resolve/main/ACORD%20Dataset%20%26%20ReadMe.zip"
LBR_REPO = "awinml/legalbench-rag"
LBR_DATASETS = ["privacy_qa", "contractnli", "maud", "cuad"]
MINI_PER_DATASET = 194
PAPER_MINI = {"queries": 776, "documents": 72, "characters": 8_682_104}


def safe_name(rel_path: str) -> str:
    """Map a repo path to a Windows-safe local path (MAUD file names contain '|')."""
    bad = '<>:"|?*'
    return "".join(f"%{ord(c):02X}" if c in bad else c for c in rel_path)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)


def get_acord() -> None:
    out = PUBLIC / "acord"
    target = out / "corpus.jsonl"
    if target.exists():
        print("ACORD already present")
        return
    zpath = out / "acord.zip"
    if not zpath.exists():
        print("Downloading ACORD ...")
        download(ACORD_ZIP, zpath)
    with zipfile.ZipFile(zpath) as z:
        for member in z.namelist():
            name = member.split("/", 1)[-1]  # drop the top-level folder
            if name in ("corpus.jsonl", "queries.jsonl") or name.startswith("qrels/"):
                if name.endswith("/"):
                    continue
                dest = out / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(member))
    print("ACORD ready:", sorted(p.name for p in out.iterdir()))


def get_legalbenchrag() -> None:
    out = PUBLIC / "legalbenchrag" / "mirror"
    out.mkdir(parents=True, exist_ok=True)
    sums_path = out / "SHA256SUMS"
    if not sums_path.exists():
        download(f"{HF}/datasets/{LBR_REPO}/resolve/main/SHA256SUMS", sums_path)
    for extra in ("README.md", "LICENSE"):
        if not (out / extra).exists():
            download(f"{HF}/datasets/{LBR_REPO}/resolve/main/{extra}", out / extra)
    expected = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, rel = line.split("  ", 1)
        expected[rel] = digest
    bad = 0
    for i, (rel, digest) in enumerate(sorted(expected.items())):
        dest = out / safe_name(rel)
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == digest:
            continue
        url = f"{HF}/datasets/{LBR_REPO}/resolve/main/{urllib.parse.quote(rel)}"
        download(url, dest)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != digest:
            print("CHECKSUM MISMATCH:", rel)
            bad += 1
        if i % 100 == 0:
            print(f"  {i}/{len(expected)} files")
    if bad:
        sys.exit(f"{bad} LegalBench-RAG files failed checksum verification")
    print(f"LegalBench-RAG mirror verified: {len(expected)} files match SHA256SUMS")
    build_mini(out)


def build_mini(mirror: Path) -> None:
    """Rebuild LegalBench-RAG-mini exactly as legalbenchrag/benchmark.py does (SORT_BY_DOCUMENT=True)."""
    tests_out, docs = [], set()
    for name in LBR_DATASETS:
        tests = json.loads((mirror / "benchmarks" / f"{name}.json").read_text(encoding="utf-8"))["tests"]
        if len(tests) > MINI_PER_DATASET:
            tests = sorted(tests, key=lambda t: (random.seed(t["snippets"][0]["file_path"]), random.random())[1])
            tests = tests[:MINI_PER_DATASET]
        for t in tests:
            t["tags"] = [name]
            docs.update(s["file_path"] for s in t["snippets"])
        tests_out.extend(tests)
    chars = sum(len((mirror / "corpus" / safe_name(d)).read_text(encoding="utf-8")) for d in docs)
    stats = {"queries": len(tests_out), "documents": len(docs), "characters": chars}
    print("Rebuilt mini:", stats, "paper:", PAPER_MINI)
    if stats != PAPER_MINI:
        sys.exit("LegalBench-RAG-mini does not match the paper's Table 3; refusing to continue")
    mini = {"tests": tests_out, "documents": sorted(docs), "stats": stats}
    (mirror.parent / "mini.json").write_text(json.dumps(mini), encoding="utf-8")
    print("Wrote", mirror.parent / "mini.json")


if __name__ == "__main__":
    get_acord()
    get_legalbenchrag()
