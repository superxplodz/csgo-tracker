"""Record a buy or sell in the encrypted site data.

  SITE_PASSWORD=... python scripts/trade.py buy  "Kilowatt Case" 50 0.15 [--date 2026-11-03]
  SITE_PASSWORD=... python scripts/trade.py sell "Kilowatt Case" 20 0.30 [--fee 15] [--date 2026-11-03]

Prices are per item in USD. A sell uses the average buy price as cost and the fee in percent
(15 = Steam). Items are matched by their exact Steam name. Commit data.enc and items.txt after.
"""
import argparse
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from crypto_box import decrypt, encrypt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA, ITEMS = os.path.join(ROOT, "data.enc"), os.path.join(ROOT, "items.txt")


def category(name):
    if name.startswith("Sticker |"):
        return "Stickers"
    if "Capsule" in name:
        return "Capsules"
    if "Souvenir Package" in name:
        return "Souvenir packages"
    if name.endswith("Case"):
        return "Cases"
    if "Music Kit" in name:
        return "Music kits"
    return "Weapon skins"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("side", choices=["buy", "sell"])
    ap.add_argument("item")
    ap.add_argument("qty", type=int)
    ap.add_argument("price", type=float)
    ap.add_argument("--fee", type=float, default=15.0)
    ap.add_argument("--date", default=datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d"))
    a = ap.parse_args()
    if a.qty <= 0 or a.price < 0:
        raise SystemExit("qty must be positive and price not negative")

    pw = os.environ["SITE_PASSWORD"]
    db = decrypt(open(DATA, encoding="utf-8").read(), pw)
    h = next((x for x in db["holdings"] if x["item"] == a.item), None)

    if a.side == "buy":
        if h is None:
            h = {"item": a.item, "category": category(a.item), "qty": 0, "cost": 0.0, "avg_buy": 0.0}
            db["holdings"].append(h)
            db["holdings"].sort(key=lambda x: x["item"])
        h["qty"] += a.qty
        h["cost"] = round(h["cost"] + a.qty * a.price, 2)
        h["avg_buy"] = round(h["cost"] / h["qty"], 4)
        print(f"Bought {a.qty} × {a.item} @ ${a.price:.2f}. Now {h['qty']} held, avg ${h['avg_buy']:.4f}.")
    else:
        if h is None or h["qty"] < a.qty:
            raise SystemExit(f"Can't sell {a.qty}: holding {h['qty'] if h else 0} of {a.item}")
        cost = round(a.qty * h["avg_buy"], 2)
        proceeds = round(a.qty * a.price * (1 - a.fee / 100), 2)
        db["sales"].append({"id": str(uuid4()), "item": a.item, "category": h["category"], "qty": a.qty,
                            "buy": h["avg_buy"], "sale": a.price, "fee_pct": a.fee, "sold_on": a.date,
                            "proceeds": proceeds, "cost": cost, "realized": round(proceeds - cost, 2)})
        h["qty"] -= a.qty
        h["cost"] = round(max(h["cost"] - cost, 0), 2)
        if h["qty"] == 0:
            db["holdings"].remove(h)
        print(f"Sold {a.qty} × {a.item} @ ${a.price:.2f} ({a.fee:g}% fee). Profit ${proceeds - cost:+.2f}.")

    with open(DATA, "w", encoding="utf-8") as f:
        f.write(encrypt(db, pw))
    with open(ITEMS, "w", encoding="utf-8") as f:
        f.write("\n".join(x["item"] for x in db["holdings"]) + "\n")


if __name__ == "__main__":
    main()
