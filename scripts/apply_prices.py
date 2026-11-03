"""Merge fetched Steam prices into the encrypted site data.

Input:  incoming/prices.json  {"_date": "YYYY-MM-DD", "_fetched_at": ISO,
                               "<item>": {"price": float, "listings": int|null, "icon": str|null}, ...}
Output: data.enc (prices + one value-history row per day) and items.txt (item names).
Needs:  SITE_PASSWORD environment variable.
"""
import json
import os
from datetime import datetime, timedelta, timezone

from crypto_box import decrypt, encrypt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data.enc")
INCOMING = os.path.join(ROOT, "incoming", "prices.json")
ITEMS = os.path.join(ROOT, "items.txt")
JAKARTA = timezone(timedelta(hours=7))


def main():
    password = os.environ["SITE_PASSWORD"]
    db = decrypt(open(DATA, encoding="utf-8").read(), password)
    new = json.load(open(INCOMING, encoding="utf-8")) if os.path.exists(INCOMING) else {}
    now = new.get("_fetched_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    day = new.get("_date") or datetime.now(JAKARTA).strftime("%Y-%m-%d")

    old = {p["item"]: p for p in db.get("prices", [])}
    prices, fresh = [], 0
    for h in db["holdings"]:
        name, prev, got = h["item"], old.get(h["item"], {}), new.get(h["item"])
        icon = (got or {}).get("icon") or prev.get("icon")
        if got and got.get("price"):
            fresh += 1
            prices.append({"item": name, "price": float(got["price"]), "listings": got.get("listings"),
                           "icon": icon, "at": now, "stale": False})
        else:
            prices.append({"item": name, "price": prev.get("price", 0), "listings": prev.get("listings"),
                           "icon": icon, "at": prev.get("at", now), "stale": True})

    pmap = {p["item"]: p["price"] for p in prices}
    row = {"day": day,
           "value": round(sum(h["qty"] * pmap[h["item"]] for h in db["holdings"]), 2),
           "cost": round(sum(h["cost"] for h in db["holdings"]), 2),
           "items": sum(h["qty"] for h in db["holdings"])}
    history = sorted([r for r in db.get("history", []) if r["day"] != day] + [row], key=lambda r: r["day"])

    db.update(prices=prices, history=history, updated_at=now)
    with open(DATA, "w", encoding="utf-8") as f:
        f.write(encrypt(db, password))
    with open(ITEMS, "w", encoding="utf-8") as f:
        f.write("\n".join(h["item"] for h in db["holdings"]) + "\n")
    print(f"{day}: {fresh}/{len(prices)} fresh prices, value ${row['value']:,.2f}")


if __name__ == "__main__":
    main()
