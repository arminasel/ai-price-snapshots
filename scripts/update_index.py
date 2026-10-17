"""Model capability scores for price/performance sorting (run by the daily workflow).

Source: the Artificial Analysis Intelligence Index (https://artificialanalysis.ai), read through its free data API.
The free API needs a key, stored as the repository secret AA_API_KEY. Without it this script changes nothing.
The list is rebuilt from the API on every run; a model with several settings gets its best score. Free use requires attribution to
artificialanalysis.ai, which AI Usage Tray shows next to the scores.

prices/index.json: {"source", "attribution", "asOf", "models": {model id: {"name", "index", "note"?}}}
Model ids follow models.dev (the price list), so the app can join scores to prices.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "prices" / "index.json"
ENDPOINTS = ("https://artificialanalysis.ai/api/v2/language/models/free",
             "https://artificialanalysis.ai/api/v2/language/models",
             "https://artificialanalysis.ai/api/v2/data/llms/models")


SETTINGS = {"max", "xhigh", "high", "medium", "low", "minimal", "ultra", "reasoning", "non", "nonreasoning", "thinking",
            "adaptive", "default", "fallback", "effort", "mode", "extended", "standard", "preview", "latest"}


def tokens(s: str) -> list[str]:
    """'gpt-5.5' and 'gpt-5-5-xhigh' share the tokens ['gpt', '5', '5']; separators do not matter."""
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def fetch(key: str) -> list:
    last = None
    for url in ENDPOINTS:
        req = urllib.request.Request(url, headers={"x-api-key": key, "User-Agent": "ai-price-snapshots"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.loads(r.read().decode("utf-8"))
            rows = body.get("data") if isinstance(body, dict) else body
            if isinstance(rows, list) and rows:
                return rows
        except Exception as e:  # noqa: BLE001 - try the next documented path
            last = e
    raise SystemExit(f"Artificial Analysis API unavailable: {last}")


def main() -> int:
    key = os.environ.get("AA_API_KEY", "").strip()
    if not key:
        print("no AA_API_KEY: index unchanged")
        return 0
    rows = fetch(key)
    hist = json.loads((ROOT / "prices" / "history.json").read_text(encoding="utf-8"))
    ids = {mid for prov in hist["snapshots"][-1]["models"].values() for mid in prov}
    id_tok = {mid: tokens(mid) for mid in ids}
    cur = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"models": {}}
    # Artificial Analysis lists several settings of one model (max, high, non-reasoning …) as separate rows. Each row
    # goes to the longest price-list id its slug starts with; per id the best score is kept, with that setting's name,
    # so "Güç" is always the model at its strongest setting.
    best: dict[str, dict] = {}
    unmatched: list[str] = []
    for r in rows:
        score = (r.get("evaluations") or {}).get("artificial_analysis_intelligence_index")
        if not isinstance(score, (int, float)):
            continue
        st = tokens(str(r.get("slug") or r.get("name") or ""))
        # the rest of the slug may only name a setting; anything else ("mini", "pro", "lite" …) is a different model
        cands = [mid for mid, t in id_tok.items() if t and st[:len(t)] == t and all(x in SETTINGS for x in st[len(t):])]
        if not cands:
            unmatched.append(str(r.get("slug") or r.get("name")))
            continue
        mid = max(cands, key=lambda m: len(id_tok[m]))
        if mid not in best or score > best[mid]["index"]:
            best[mid] = {"name": str(r.get("name") or mid)[:80], "index": round(float(score), 1)}
    print("unmatched (no price-list id):", ", ".join(sorted(unmatched)[:200]))   # public slugs only, for mapping fixes
    if len(best) < 5:
        print(f"only {len(best)} scores matched; index unchanged")
        return 0
    models = best
    hits = len(best)
    out = {"source": "https://artificialanalysis.ai", "attribution": "Artificial Analysis Intelligence Index",
           "asOf": datetime.now(timezone.utc).date().isoformat(), "rule": "best score across a model's listed settings",
           "models": dict(sorted(models.items()))}
    if json.dumps(out.get("models")) != json.dumps(cur.get("models")):
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"changed ({hits} scores)")
    else:
        print("unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
