"""Daily job: pull Steam Market prices for every holding and add a history row.

Reads and writes data.enc (encrypted). Needs the SITE_PASSWORD env var.
Run by .github/workflows/update-prices.yml.
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from crypto_box import encrypt, decrypt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data.enc")
URL = "https://steamcommunity.com/market/priceoverview/?appid=730&currency=1&market_hash_name="
DELAY = float(os.environ.get("STEAM_DELAY", "6"))  # seconds between calls; Steam allows ~20/min per IP
FRESH_HOURS = 20       # items priced within this window are skipped, so each run only does what's left
MAX_429_STREAK = 3     # after this many rate-limits in a row, stop and save; the next run continues


class RateLimited(Exception):
    pass
JAKARTA = timezone(timedelta(hours=7))


def money(s):
    if not s:
        return None
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def fetch(name):
    req = urllib.request.Request(URL + urllib.parse.quote(name, safe=""),
                                 headers={"User-Agent": "Mozilla/5.0 (cs2-skin-tracker)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                j = json.load(r)
            if not j.get("success"):
                return None
            price = money(j.get("lowest_price")) or money(j.get("median_price"))
            if price is None:
                return None
            vol = j.get("volume")
            return {"price": price, "median": money(j.get("median_price")),
                    "volume_24h": int(vol.replace(",", "")) if vol else None}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimited()
            if e.code >= 500:
                time.sleep(10)
                continue
            return None
        except Exception as e:  # network hiccup
            print(f"  error {e}", flush=True)
            time.sleep(10)
    return None


def file_fetcher(path):
    """Prices fetched elsewhere: JSON {item: {"price":..,"median":..,"volume_24h":..} or null}."""
    got = json.load(open(path, encoding="utf-8"))
    def fetch_from_file(name):
        r = got.get(name)
        return r if r and r.get("price") else None
    return fetch_from_file


def main():
    pw = os.environ.get("SITE_PASSWORD")
    if not pw:
        sys.exit("SITE_PASSWORD is not set")
    db = decrypt(open(DATA, encoding="utf-8").read(), pw)
    old = {p["item"]: p for p in db.get("prices", [])}
    now_dt = datetime.now(timezone.utc)
    now = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def fresh(p):
        if not p or not (p.get("source") or "").startswith("Steam lowest"):
            return False
        try:
            at = datetime.strptime(p["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except Exception:
            return False
        return (now_dt - at).total_seconds() < FRESH_HOURS * 3600

    todo = [h["item"] for h in db["holdings"] if not fresh(old.get(h["item"]))]
    print(f"{len(todo)} of {len(db['holdings'])} items need a price", flush=True)
    if "--list" in sys.argv:  # print the items that still need a price, one per line, then stop
        out = sys.argv[sys.argv.index("--list") + 1] if len(sys.argv) > sys.argv.index("--list") + 1 else None
        text = "\n".join(f"{n}\t{URL + urllib.parse.quote(n, safe='')}" for n in todo)
        if out:
            open(out, "w", encoding="utf-8").write(text + "\n")
        else:
            print(text)
        return
    fetch_fn, delay = fetch, DELAY
    if os.environ.get("PRICES_FILE"):
        fetch_fn, delay = file_fetcher(os.environ["PRICES_FILE"]), 0
    got_map, streak, stopped = {}, 0, False
    for i, name in enumerate(todo):
        try:
            got = fetch_fn(name)
            streak = 0
        except RateLimited:
            streak += 1
            print(f"[{i + 1}/{len(todo)}] {name}: rate limited ({streak} in a row)", flush=True)
            if streak >= MAX_429_STREAK:
                print("Steam is rate-limiting this server. Saving progress; the next run continues.", flush=True)
                stopped = True
                break
            time.sleep(90)
            continue
        if got:
            got_map[name] = got
        print(f"[{i + 1}/{len(todo)}] {name}: {got['price'] if got else 'no price'}", flush=True)
        time.sleep(delay)

    today = datetime.now(JAKARTA).strftime("%Y-%m-%d")
    if not got_map and any(r["day"] == today for r in db.get("history", [])):
        print("Nothing new to save. Password OK, data unchanged.")
        return

    prices, failed = [], []
    for h in db["holdings"]:
        name = h["item"]
        if name in got_map:
            prices.append({"item": name, **got_map[name], "source": "Steam lowest listing", "at": now})
        elif fresh(old.get(name)):
            prices.append(old[name])
        else:
            prev = old.get(name, {})
            failed.append(name)
            prices.append({"item": name, "price": prev.get("price", 0), "median": prev.get("median"),
                           "volume_24h": prev.get("volume_24h"), "source": "Previous price (Steam fetch failed)",
                           "at": prev.get("at", now)})

    pmap = {p["item"]: p["price"] for p in prices}
    value = round(sum(h["qty"] * pmap[h["item"]] for h in db["holdings"]), 2)
    cost = round(sum(h["cost"] for h in db["holdings"]), 2)
    day = datetime.now(JAKARTA).strftime("%Y-%m-%d")
    hist = [r for r in db.get("history", []) if r["day"] != day]
    hist.append({"day": day, "value": value, "cost": cost, "items": sum(h["qty"] for h in db["holdings"])})
    hist.sort(key=lambda r: r["day"])

    db.update(prices=prices, history=hist, updated_at=now)
    open(DATA, "w", encoding="utf-8").write(encrypt(db, pw))
    print(f"Done. Value ${value:,.2f}, cost ${cost:,.2f}. Failed: {len(failed)}")
    for f in failed:
        print("  failed:", f)
    if stopped:
        print(f"Stopped early: {len(failed)} items still waiting for a fresh price.")


if __name__ == "__main__":
    main()
