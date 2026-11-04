"""Fetch Steam Community Market prices for every item in items.txt.

Writes incoming/prices.json in the format apply_prices.py reads:
  {"_date": "YYYY-MM-DD", "_fetched_at": ISO,
   "<item>": {"price": float, "listings": int|null, "icon": str|null}, ...}

To keep requests (and Steam rate-limiting) low it first runs a few broad searches
that cover many items at once (for example "Holo Paris 2023" for all Paris 2023 Holo
stickers, or "Rio 2022 Capsule" for every Rio 2022 capsule), up to 100 results per page.
Anything those miss is then looked up by its exact name.

Requests are spaced out, and on HTTP 429 the script waits and retries. If Steam keeps
refusing, it stops and saves whatever it found; items without a new price keep their
previous price on the site. Prices already fetched earlier the same day (Jakarta time)
are kept for items this run could not reach.

Exit code is 0 even with a partial result, so the found prices still get applied.
Prints price alerts (moves of 10% or more on items worth at least $0.10) against the
previous day's prices, and writes them to the GitHub job summary when available.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEMS = os.path.join(ROOT, "items.txt")
OUT = os.path.join(ROOT, "incoming", "prices.json")
JAKARTA = timezone(timedelta(hours=7))

SEARCH = "https://steamcommunity.com/market/search/render/"
PAGE = 100            # Steam's maximum page size
MAX_PAGES = 4         # per broad search
DELAY = float(os.environ.get("STEAM_DELAY", "4"))      # seconds between requests
RETRY_WAITS = (30, 90, 180)                            # waits after an HTTP 429
MAX_REQUESTS = int(os.environ.get("STEAM_MAX_REQUESTS", "80"))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

EVENT = r"([A-Z][a-z]+ \d{4})"


class RateLimited(Exception):
    pass


class Steam:
    def __init__(self):
        self.requests = 0
        self.last = 0.0

    def search(self, query, start=0, count=PAGE):
        if self.requests >= MAX_REQUESTS:
            raise RateLimited(f"request budget of {MAX_REQUESTS} used up")
        params = {"appid": 730, "norender": 1, "query": query, "start": start, "count": count,
                  "search_descriptions": 0, "sort_column": "name", "sort_dir": "asc"}
        url = SEARCH + "?" + urllib.parse.urlencode(params)
        for wait in (0,) + RETRY_WAITS:
            if wait:
                print(f"  rate-limited, waiting {wait}s")
                time.sleep(wait)
            gap = DELAY - (time.monotonic() - self.last)
            if gap > 0:
                time.sleep(gap)
            self.last = time.monotonic()
            self.requests += 1
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
                    body = r.read()
            except urllib.error.HTTPError as e:
                if e.code in (429, 503):
                    continue
                print(f"  HTTP {e.code} for {query!r}")
                return None
            except Exception as e:  # network hiccup: try again after a pause
                print(f"  error for {query!r}: {e}")
                continue
            try:
                data = json.loads(body)
            except ValueError:
                continue
            if not data or not data.get("success"):
                continue  # Steam answers {"success": false} or null when throttling
            return data
        raise RateLimited(f"Steam kept refusing ({query!r})")


def plan(items):
    """Group items into broad searches. Returns {query: set(items)}; singles are left out."""
    groups = defaultdict(set)
    for n in items:
        m = re.match(r"^Sticker \| .+ \((Holo|Foil|Gold|Glitter)\) \| " + EVENT + "$", n)
        if m:
            groups[f"{m.group(1)} {m.group(2)}"].add(n)
            continue
        m = re.match("^" + EVENT + r" .*(Capsule|Souvenir Package)$", n)
        if m:
            groups[f"{m.group(1)} {m.group(2)}"].add(n)
    return {q: s for q, s in groups.items() if len(s) >= 2}


def record(found, wanted, results):
    for r in results or []:
        name = r.get("hash_name")
        if name in wanted and r.get("sell_price"):
            found[name] = {"price": round(r["sell_price"] / 100, 2),
                           "listings": r.get("sell_listings"),
                           "icon": (r.get("asset_description") or {}).get("icon_url")}


def fetch(items):
    steam, found, wanted = Steam(), {}, set(items)
    try:
        for query, members in sorted(plan(items).items(), key=lambda kv: -len(kv[1])):
            if members <= found.keys():
                continue
            for page in range(MAX_PAGES):
                data = steam.search(query, start=page * PAGE)
                if not data:
                    break
                record(found, wanted, data.get("results"))
                total = data.get("total_count") or 0
                print(f"{query!r} page {page + 1}: {total} results, {len(members & found.keys())}/{len(members)} found")
                if members <= found.keys() or (page + 1) * PAGE >= total:
                    break
        for name in items:
            if name in found:
                continue
            data = steam.search(name, count=10)
            if data:
                record(found, wanted, data.get("results"))
            print(f"{name!r}: {'found' if name in found else 'not found'}")
    except RateLimited as e:
        print(f"Stopped early: {e}")
    print(f"{steam.requests} requests")
    return found


def alerts(new, old):
    rows = []
    for name, v in new.items():
        before, after = (old.get(name) or {}).get("price"), v["price"]
        if before and after >= 0.10 and abs(after - before) / before >= 0.10:
            rows.append((abs(after - before) / before, f"{name} ${before:.2f} → ${after:.2f} ({(after - before) / before:+.0%})"))
    return [line for _, line in sorted(rows, reverse=True)]


def main():
    items = [l.strip() for l in open(ITEMS, encoding="utf-8") if l.strip()]
    previous = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    today = datetime.now(JAKARTA).strftime("%Y-%m-%d")
    same_day = previous.get("_date") == today

    found = fetch(items)

    merged = {k: v for k, v in previous.items() if not k.startswith("_") and k in items} if same_day else {}
    merged.update(found)
    changed = any(previous.get(k) != v for k, v in merged.items())
    missing = [n for n in items if n not in merged]

    report = []
    if not same_day and previous:
        moves = alerts(found, previous)
        report.append("**Price alerts:** " + ("none" if not moves else ""))
        report += [f"- {m}" for m in moves]
        report.append("")
    report.append(f"**{len(merged)}/{len(items)} items priced today** ({len(found)} fetched this run).")
    if missing:
        report.append(f"\nStill missing ({len(missing)}), keeping their previous price:")
        report += [f"- {n}" for n in missing]
    report = "\n".join(report)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(report + "\n")

    if not found or not changed:
        print("No new prices, leaving incoming/prices.json unchanged.")
        return
    out = {"_date": today, "_fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    out.update({n: merged[n] for n in items if n in merged})
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"count={len(merged)}\n")


if __name__ == "__main__":
    sys.exit(main())
