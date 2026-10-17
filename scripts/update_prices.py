"""Daily price snapshot (run by .github/workflows/prices.yml on a GitHub runner, not on the user's PC).

Reads https://models.dev/api.json — the open model catalogue maintained by the OpenCode team, which lists each
provider's API list prices with a link to the provider's own pricing documentation — and keeps the providers this app
prices (Anthropic, OpenAI, Google, OpenCode Zen, OpenCode Go). A new snapshot is appended to prices/history.json only
when a price changes, and the change is described in prices/CHANGELOG.md, so the file is a dated record of
"on this date the prices were these". Standard library only.

Usage: python scripts/update_prices.py [--source FILE]   (exit 0; prints "changed" or "unchanged")
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "prices"
URL = "https://models.dev/api.json"
PROVIDERS = ("anthropic", "openai", "google", "opencode", "opencode-go")
FIELDS = ("input", "output", "cache_read", "cache_write")


def fetch(source: str | None) -> dict:
    if source:
        return json.loads(Path(source).read_text(encoding="utf-8"))
    req = urllib.request.Request(URL, headers={"User-Agent": "ai-usage-tray-price-snapshot"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def extract(raw: dict) -> dict:
    """{provider: {model id: {name, release, input, output, cache_read, cache_write, long}}} — numbers USD per 1M."""
    out: dict[str, dict] = {}
    for prov in PROVIDERS:
        models = (raw.get(prov) or {}).get("models") or {}
        rows = {}
        for mid, m in sorted(models.items()):
            cost = m.get("cost") or {}
            if not isinstance(cost.get("input"), (int, float)) or not isinstance(cost.get("output"), (int, float)):
                continue
            row = {"name": str(m.get("name") or mid)[:80], "release": str(m.get("release_date") or "")[:10]}
            for f in FIELDS:
                v = cost.get(f)
                row[f] = float(v) if isinstance(v, (int, float)) else None
            tiers = cost.get("tiers") or []
            if tiers and isinstance(tiers[0], dict):
                t = tiers[0]
                row["long"] = {"over": (t.get("tier") or {}).get("size"), **{f: t.get(f) for f in FIELDS if isinstance(t.get(f), (int, float))}}
            rows[mid] = row
        if rows:
            out[prov] = rows
    return out


def diff(old: dict, new: dict) -> list[str]:
    lines = []
    for prov in sorted(set(old) | set(new)):
        a, b = old.get(prov, {}), new.get(prov, {})
        for mid in sorted(set(b) - set(a)):
            lines.append(f"- {prov}/{mid}: yeni ({_fmt(b[mid])})")
        for mid in sorted(set(a) - set(b)):
            lines.append(f"- {prov}/{mid}: listeden çıktı")
        for mid in sorted(set(a) & set(b)):
            if any(a[mid].get(f) != b[mid].get(f) for f in FIELDS):
                lines.append(f"- {prov}/{mid}: {_fmt(a[mid])} → {_fmt(b[mid])}")
    return lines


def _fmt(r: dict) -> str:
    return " / ".join("—" if r.get(f) is None else f"${r[f]:g}" for f in FIELDS)


def main() -> int:
    src = sys.argv[sys.argv.index("--source") + 1] if "--source" in sys.argv else None
    models = extract(fetch(src))
    if sum(len(v) for v in models.values()) < 20:
        print("refusing: the catalogue looks truncated", file=sys.stderr)
        return 1
    OUT.mkdir(exist_ok=True)
    hist_path = OUT / "history.json"
    hist = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else {"source": URL, "snapshots": []}
    prev = hist["snapshots"][-1]["models"] if hist["snapshots"] else {}
    changes = diff(prev, models)
    if not changes:
        print("unchanged")
        return 0
    today = datetime.now(timezone.utc).date().isoformat()
    if hist["snapshots"] and hist["snapshots"][-1]["date"] == today:
        hist["snapshots"][-1]["models"] = models      # one snapshot per day
    else:
        hist["snapshots"].append({"date": today, "models": models})
    hist_path.write_text(json.dumps(hist, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log = OUT / "CHANGELOG.md"
    head = "# Fiyat değişiklikleri\n\nKaynak: https://models.dev/api.json (USD / 1M token: girdi / çıktı / önbellek okuma / önbellek yazma).\n"
    body = log.read_text(encoding="utf-8")[len(head):] if log.exists() else ""
    entry = f"\n## {today}\n\n" + ("İlk kayıt: " + ", ".join(f"{p} {len(v)} model" for p, v in models.items()) + "\n" if not prev else "\n".join(changes) + "\n")
    log.write_text(head + entry + body, encoding="utf-8")
    print("changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
