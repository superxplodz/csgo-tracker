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
DELAY = float(os.environ.get("STEAM_DELAY", "3.5"))  # seconds between calls; Steam rate-limits hard
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
    for attempt in range(4):
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
                wait = 60 * (attempt + 1)
                print(f"  429 rate limit, waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            if e.code >= 500:
                time.sleep(10)
                continue
            return None
        except Exception as e:  # network hiccup
            print(f"  error {e}", flush=True)
            time.sleep(10)
    return None


def main():
    pw = os.environ.get("SITE_PASSWORD")
    if not pw:
        sys.exit("SITE_PASSWORD is not set")
    db = decrypt(open(DATA).read(), pw)
    old = {p["item"]: p for p in db.get("prices", [])}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prices, failed = [], []
    for i, h in enumerate(db["holdings"]):
        name = h["item"]
        got = fetch(name)
        if got:
            prices.append({"item": name, **got, "source": "Steam lowest listing", "at": now})
        else:
            prev = old.get(name, {})
            failed.append(name)
            prices.append({"item": name, "price": prev.get("price", 0), "median": prev.get("median"),
                           "volume_24h": None, "source": "Previous price (Steam fetch failed)",
                           "at": prev.get("at", now)})
        print(f"[{i + 1}/{len(db['holdings'])}] {name}: {prices[-1]['price']}", flush=True)
        time.sleep(DELAY)

    pmap = {p["item"]: p["price"] for p in prices}
    value = round(sum(h["qty"] * pmap[h["item"]] for h in db["holdings"]), 2)
    cost = round(sum(h["cost"] for h in db["holdings"]), 2)
    day = datetime.now(JAKARTA).strftime("%Y-%m-%d")
    hist = [r for r in db.get("history", []) if r["day"] != day]
    hist.append({"day": day, "value": value, "cost": cost, "items": sum(h["qty"] for h in db["holdings"])})
    hist.sort(key=lambda r: r["day"])

    db.update(prices=prices, history=hist, updated_at=now)
    open(DATA, "w").write(encrypt(db, pw))
    print(f"Done. Value ${value:,.2f}, cost ${cost:,.2f}. Failed: {len(failed)}")
    for f in failed:
        print("  failed:", f)
    # Fail the run if Steam blocked almost everything, so you get an email from GitHub.
    if len(failed) > len(prices) * 0.5:
        sys.exit("More than half of the price checks failed")


if __name__ == "__main__":
    main()
