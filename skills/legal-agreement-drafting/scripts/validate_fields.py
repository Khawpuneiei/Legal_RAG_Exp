"""Deterministic request checks for the legal-agreement-drafting skill.

Usage:  python skills/legal-agreement-drafting/scripts/validate_fields.py request.json
where request.json is {"agreement_type": ..., "form": {...}, "text": "..."}; prints the issues as JSON.
It calls the same Validation Engine the production workflow uses (src/agreement/validation.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.agreement.library import load_library  # noqa: E402
from src.agreement.validation import check_request  # noqa: E402


def main() -> None:
    req = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    issues = check_request(load_library(), req["agreement_type"], req.get("form", {}), req.get("text", ""))
    print(json.dumps(issues, indent=2))


if __name__ == "__main__":
    main()
