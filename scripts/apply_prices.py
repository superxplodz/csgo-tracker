"""Merge fetched Steam prices into the encrypted site data.

Input:  incoming/prices.json  {"_date": "YYYY-MM-DD", "_fetched_at": ISO,
                               "<item>": {"price": float, "listings": int|null, "icon": str|null}, ...}
Also fetches (best effort, skipped on any error):
  - Skinport lowest listing per item  (second price source)
  - USD -> IDR exchange rate
Output: data.enc (prices, per-item price history, daily value history) and items.txt.
Needs:  SITE_PASSWORD environment variable.
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

from crypto_box import decrypt, encrypt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data.enc")
INCOMING = os.path.join(ROOT, "incoming", "prices.json")
ITEMS = os.path.join(ROOT, "items.txt")
JAKARTA = timezone(timedelta(hours=7))
ITEM_HISTORY_DAYS = 180


def get_json(url, brotli_ok=False):
    headers = {"User-Agent": "csgo-tracker", "Accept-Encoding": "br" if brotli_ok else "identity"}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "br":
            import brotli
            body = brotli.decompress(body)
    return json.loads(body)


def skinport_prices():
    try:
        rows = get_json("https://api.skinport.com/v1/items?app_id=730&currency=USD&tradable=0", brotli_ok=True)
        return {r["market_hash_name"]: r["min_price"] for r in rows if r.get("min_price")}
    except Exception as e:  # never block the Steam update on this
        print(f"Skinport skipped: {e}")
        return {}


def usd_idr():
    try:
        return float(get_json("https://open.er-api.com/v6/latest/USD")["rates"]["IDR"])
    except Exception as e:
        print(f"FX skipped: {e}")
        return None


def main():
    password = os.environ["SITE_PASSWORD"]
    db = decrypt(open(DATA, encoding="utf-8").read(), password)
    new = json.load(open(INCOMING, encoding="utf-8")) if os.path.exists(INCOMING) else {}
    now = new.get("_fetched_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    day = new.get("_date") or datetime.now(JAKARTA).strftime("%Y-%m-%d")
    skinport = skinport_prices()

    old = {p["item"]: p for p in db.get("prices", [])}
    item_history = db.setdefault("item_history", {})
    prices, fresh = [], 0
    for h in db["holdings"]:
        name, prev, got = h["item"], old.get(h["item"], {}), new.get(h["item"]) or {}
        entry = {"item": name, "icon": got.get("icon") or prev.get("icon"),
                 "skinport": skinport.get(name, prev.get("skinport"))}
        if got.get("price"):
            fresh += 1
            entry.update(price=float(got["price"]), listings=got.get("listings"), at=now, stale=False)
            series = [p for p in item_history.get(name, []) if p[0] != day] + [[day, entry["price"]]]
            item_history[name] = sorted(series)[-ITEM_HISTORY_DAYS:]
        else:
            entry.update(price=prev.get("price", 0), listings=prev.get("listings"), at=prev.get("at", now), stale=True)
        prices.append(entry)

    pmap = {p["item"]: p["price"] for p in prices}
    row = {"day": day,
           "value": round(sum(h["qty"] * pmap[h["item"]] for h in db["holdings"]), 2),
           "cost": round(sum(h["cost"] for h in db["holdings"]), 2),
           "items": sum(h["qty"] for h in db["holdings"])}
    history = sorted([r for r in db.get("history", []) if r["day"] != day] + [row], key=lambda r: r["day"])

    rate = usd_idr()
    if rate:
        db["fx"] = {"IDR": rate, "at": now}
    db.update(prices=prices, history=history, updated_at=now)
    with open(DATA, "w", encoding="utf-8") as f:
        f.write(encrypt(db, password))
    with open(ITEMS, "w", encoding="utf-8") as f:
        f.write("\n".join(h["item"] for h in db["holdings"]) + "\n")
    print(f"{day}: {fresh}/{len(prices)} Steam prices, {sum(1 for p in prices if p['skinport'])} Skinport, "
          f"value ${row['value']:,.2f}")


if __name__ == "__main__":
    main()
