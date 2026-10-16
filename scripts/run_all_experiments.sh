#!/usr/bin/env bash
# Runs every remaining experiment end to end (about 9 hours on an RTX 4060 laptop GPU).
# Uses a second Ollama server with parallel decoding (OLLAMA_NUM_PARALLEL=4, flash attention, q8_0 KV cache) on port 11435:
#   OLLAMA_HOST=127.0.0.1:11435 OLLAMA_NUM_PARALLEL=4 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve
set -euo pipefail
cd "$(dirname "$0")/.."
export OLLAMA_HOST=${OLLAMA_HOST:-http://127.0.0.1:11435}
PY=${PY:-.venv/Scripts/python.exe}
echo "start $(date)"
$PY eval/exp12.py --exp 2 --workers 4
$PY eval/exp12.py --exp 1 --workers 4
$PY eval/generation_eval_graph.py
$PY eval/judge.py
echo "done $(date)"
