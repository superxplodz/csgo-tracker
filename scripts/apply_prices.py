"""Daily price update for the encrypted site data. Runs on GitHub Actions.

Steam prices come from the public CSGO Trader price feed (prices.csgotrader.app), which
mirrors Steam Community Market sales: the average sale price over the last 24 hours
(falling back to 7, 30 or 90 days). One request covers every item, so Steam's rate limits
don't apply. Optional manual prices in incoming/prices.json fill any gaps:
  {"<item>": {"price": float, "icon": str|null}, ...}
Also fetches (best effort, skipped on any error):
  - Skinport lowest listing per item  (second price source)
  - USD -> IDR exchange rate
  - Steam inventory check: compares the public inventory with holdings and flags
    differences for review (it never changes holdings)
Output: data.enc (prices, per-item price history, daily value history) and items.txt.
Needs:  SITE_PASSWORD environment variable.
"""
import gzip
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
    if body[:2] == b"\x1f\x8b":  # gzip, sent by some servers regardless of Accept-Encoding
        body = gzip.decompress(body)
    return json.loads(body)


def steam_feed():
    try:
        feed = get_json("https://prices.csgotrader.app/latest/steam.json", brotli_ok=False)
    except Exception as e:
        print(f"Steam feed skipped: {e}")
        return {}
    out = {}
    for name, p in feed.items():
        price = next((p.get(k) for k in ("last_24h", "last_7d", "last_30d", "last_90d") if isinstance(p, dict) and p.get(k)), None)
        if price:
            out[name] = float(price)
    return out


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


def inventory_check(steam_id, holdings, previous):
    """Count marketable CS2 items in the public inventory and list differences with holdings."""
    url = f"https://steamcommunity.com/inventory/{steam_id}/730/2?l=english&count=2000"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        inv = get_json(url)
    except Exception as e:
        print(f"Inventory skipped: {e}")
        return {**(previous or {}), "status": f"error: {e}", "tried_at": now}
    names = {(d["classid"], d["instanceid"]): d["market_hash_name"] for d in inv.get("descriptions", []) if d.get("marketable")}
    counts = {}
    for a in inv.get("assets", []):
        n = names.get((a["classid"], a["instanceid"]))
        if n:
            counts[n] = counts.get(n, 0) + int(a.get("amount", 1))
    held = {h["item"]: h["qty"] for h in holdings}
    fewer = [{"item": n, "held": q, "in_inventory": counts.get(n, 0)} for n, q in held.items() if counts.get(n, 0) < q]
    untracked = [{"item": n, "in_inventory": c, "held": held.get(n, 0)} for n, c in counts.items() if c > held.get(n, 0)]
    print(f"Inventory: {sum(counts.values())} marketable items, {len(fewer)} fewer than held, {len(untracked)} untracked")
    return {"status": "ok", "at": now, "tried_at": now, "fewer": sorted(fewer, key=lambda r: r["item"]),
            "untracked": sorted(untracked, key=lambda r: r["item"])}


def main():
    password = os.environ["SITE_PASSWORD"]
    db = decrypt(open(DATA, encoding="utf-8").read(), password)
    manual = json.load(open(INCOMING, encoding="utf-8")) if os.path.exists(INCOMING) else {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    day = datetime.now(JAKARTA).strftime("%Y-%m-%d")
    feed = steam_feed()
    if not feed:
        raise SystemExit("Steam feed unavailable; data left unchanged")
    skinport = skinport_prices()
    new = {n: {"price": feed[n]} for n in feed}
    for n, v in manual.items():  # manual prices only fill gaps in the feed
        if not n.startswith("_") and isinstance(v, dict) and n not in new:
            new[n] = v
    if feed and db.get("price_source") != "csgotrader":
        db["price_source"] = "csgotrader"
        db["source_changed"] = day  # marked on the value chart

    old = {p["item"]: p for p in db.get("prices", [])}
    item_history = db.setdefault("item_history", {})
    prices, fresh = [], 0
    for h in db["holdings"]:
        name, prev, got = h["item"], old.get(h["item"], {}), new.get(h["item"]) or {}
        entry = {"item": name, "icon": got.get("icon") or prev.get("icon") or db.get("icons", {}).get(name),
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

    if db.get("steam_id"):
        db["inventory_check"] = inventory_check(db["steam_id"], db["holdings"], db.get("inventory_check"))
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
