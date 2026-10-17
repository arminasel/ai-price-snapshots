"""Model capability scores for price/performance sorting (run by the daily workflow).

Source: the Artificial Analysis Intelligence Index (https://artificialanalysis.ai), read through its free data API.
The free API needs a key: create one at https://artificialanalysis.ai and store it as the repository secret
AA_API_KEY. Without the secret this script changes nothing, and prices/index.json keeps its last values (the first
values were copied from a manual reading of the leaderboard on 2026-10-10). Free use requires attribution to
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


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


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
    by_norm = {norm(i): i for i in ids}
    cur = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"models": {}}
    models = dict(cur.get("models") or {})
    hits = 0
    for r in rows:
        ev = r.get("evaluations") or {}
        score = ev.get("artificial_analysis_intelligence_index")
        if not isinstance(score, (int, float)):
            continue
        for cand in (r.get("slug"), r.get("name"), (r.get("model_creator") or {}).get("slug", "") + "-" + str(r.get("slug"))):
            mid = by_norm.get(norm(str(cand or "")))
            if mid:
                models[mid] = {"name": r.get("name") or mid, "index": round(float(score), 1)}
                hits += 1
                break
    if not hits:
        print("no scores matched; index unchanged")
        return 0
    out = {"source": "https://artificialanalysis.ai", "attribution": "Artificial Analysis Intelligence Index",
           "asOf": datetime.now(timezone.utc).date().isoformat(), "models": dict(sorted(models.items()))}
    if json.dumps(out.get("models")) != json.dumps(cur.get("models")):
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"changed ({hits} scores)")
    else:
        print("unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
