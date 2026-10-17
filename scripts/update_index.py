"""Model capability scores per reasoning setting, for price/performance sorting (run by the daily workflow).

Source: the Artificial Analysis Intelligence Index (https://artificialanalysis.ai), read through its free data API
with the repository secret AA_API_KEY (without it this script changes nothing). Free use requires attribution to
artificialanalysis.ai, which AI Usage Tray shows next to the scores.

Artificial Analysis measures many models at several settings (Low … Max, reasoning on/off); each one is kept as its
own variant. The free API returns only part of the catalogue, so prices/index-manual.json adds model/setting pairs
read by hand from the public leaderboard; an API value always replaces a manual one for the same pair.

prices/index.json: {"source", "attribution", "asOf", "rule",
                    "models": {model id: {"name", "index" (best), "variants": [{"setting", "index", "source"}]}}}
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
MANUAL = ROOT / "prices" / "index-manual.json"
ENDPOINTS = ("https://artificialanalysis.ai/api/v2/language/models/free",
             "https://artificialanalysis.ai/api/v2/language/models",
             "https://artificialanalysis.ai/api/v2/data/llms/models")
# words that name a setting of the same model; any other trailing word ("mini", "pro", "lite" …) is a different model
SETTINGS = {"max", "xhigh", "high", "medium", "low", "minimal", "ultra", "reasoning", "non", "nonreasoning", "thinking",
            "adaptive", "default", "fallback", "effort", "mode", "extended", "standard", "preview", "latest", "exp"}
# words on the price-list side that do not change the model ("-free" tiers, "-preview" names)
ID_NOISE = {"free", "preview", "latest"}


def tokens(s: str) -> list[str]:
    """'gpt-5.5' and 'gpt-5-5-xhigh' share the tokens ['gpt', '5', '5']; separators do not matter."""
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def core(mid: str) -> list[str]:
    t = tokens(mid.split("/")[-1])
    while t and t[-1] in ID_NOISE:
        t.pop()
    return t


def is_setting_tail(rest: list[str]) -> bool:
    return all(x in SETTINGS or (x.isdigit() and len(x) >= 4) for x in rest)   # dated releases: -0424, -2507


def setting_of(name: str, rest: list[str]) -> str:
    m = re.search(r"\(([^)]*)\)", name or "")
    if m:
        parts = [p.strip() for p in m.group(1).split(",") if p.strip() and p.strip().lower() not in ("default fallback", "default")]
        if parts:
            return " ".join(parts)
    words = [w for w in rest if not w.isdigit() and w not in ("default", "fallback", "effort", "mode")]
    return " ".join(w.capitalize() for w in words) or "Varsayılan"


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


def build(rows: list, ids: set[str], manual: dict) -> tuple[dict, list[str]]:
    id_tok = {mid: core(mid) for mid in ids}
    variants: dict[str, dict[str, dict]] = {}
    names: dict[str, str] = {}
    unmatched = []
    for r in rows:
        score = (r.get("evaluations") or {}).get("artificial_analysis_intelligence_index")
        if not isinstance(score, (int, float)):
            continue
        name = str(r.get("name") or "")
        st = tokens(str(r.get("slug") or name))
        cands = [mid for mid, t in id_tok.items() if t and st[:len(t)] == t and is_setting_tail(st[len(t):])]
        if not cands:
            unmatched.append(str(r.get("slug") or name))
            continue
        best_len = max(len(id_tok[m]) for m in cands)
        setting = setting_of(name, st[best_len:])
        for mid in (m for m in cands if len(id_tok[m]) == best_len):   # e.g. "x-free" and "x" share one score
            v = variants.setdefault(mid, {})
            if setting not in v or score > v[setting]["index"]:
                v[setting] = {"setting": setting, "index": round(float(score), 1), "source": "api"}
            names.setdefault(mid, re.sub(r"\s*\([^)]*\)", "", name).strip() or mid)
    for mid, settings in (manual.get("models") or {}).items():
        for setting, score in settings.items():
            v = variants.setdefault(mid, {})
            if setting not in v:
                v[setting] = {"setting": setting, "index": float(score), "source": "manual"}
    models = {}
    for mid, v in sorted(variants.items()):
        vs = sorted(v.values(), key=lambda x: -x["index"])
        models[mid] = {"name": names.get(mid, mid), "index": vs[0]["index"], "variants": vs}
    return models, unmatched


def main() -> int:
    key = os.environ.get("AA_API_KEY", "").strip()
    if not key:
        print("no AA_API_KEY: index unchanged")
        return 0
    rows = fetch(key)
    hist = json.loads((ROOT / "prices" / "history.json").read_text(encoding="utf-8"))
    ids = {mid for prov in hist["snapshots"][-1]["models"].values() for mid in prov}
    manual = json.loads(MANUAL.read_text(encoding="utf-8")) if MANUAL.exists() else {}
    models, unmatched = build(rows, ids, manual)
    print(f"API rows {len(rows)}; models with a score {len(models)}; unmatched API rows {len(unmatched)}")
    print("unmatched (no price-list id):", ", ".join(sorted(unmatched)[:250]))   # public slugs only, for mapping fixes
    if sum(1 for m in models.values() if any(v["source"] == "api" for v in m["variants"])) < 5:
        print("too few API matches; index unchanged")
        return 0
    cur = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"models": {}}
    out = {"source": "https://artificialanalysis.ai", "attribution": "Artificial Analysis Intelligence Index",
           "asOf": datetime.now(timezone.utc).date().isoformat(), "manualAsOf": manual.get("asOf"),
           "rule": "every listed setting kept; index = best setting", "models": models}
    if json.dumps(out["models"], sort_keys=True) != json.dumps(cur.get("models"), sort_keys=True):
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"changed ({len(models)} models)")
    else:
        print("unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
