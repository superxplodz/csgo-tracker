# CS2 skin portfolio tracker

Password-protected portfolio site at **https://skins.bekasibro.my.id**, served by GitHub Pages.

| File | What it is |
|---|---|
| `index.html` | The whole site. Decrypts `data.enc` in the browser with the password. |
| `data.enc` | Holdings, prices, sales and value history, AES-256-GCM encrypted. |
| `items.txt` | Item names only, for the daily price fetch. |
| `incoming/prices.json` | Latest fetched prices (plain), pushed by the daily task. |
| `scripts/apply_prices.py` | Merges `incoming/prices.json` into `data.enc`. |
| `scripts/trade.py` | Record a buy or sell (updates holdings, sales and `items.txt`). |
| `scripts/data_tool.py` | Open, edit and re-seal `data.enc` by hand, or change the password. |
| `scripts/crypto_box.py` | Encryption shared by both scripts (browser-compatible). |
| `.github/workflows/apply-prices.yml` | Runs `apply_prices.py` when new prices are pushed. |

## How prices update

1. A Claude scheduled task (06:47 and 13:47 WIB) looks up each item in `items.txt` on the
   Steam Community Market and pushes `incoming/prices.json`. It never sees the password.
2. The **Apply prices** workflow merges them into `data.enc` using the `SITE_PASSWORD`
   repository secret. Items without a new price keep the last one and show in orange.
   It also stores each item's daily price (for the trend lines), the Skinport lowest
   listing (second price source) and the USD→IDR rate.

## Recording trades

```
SITE_PASSWORD='…' python scripts/trade.py buy  "Kilowatt Case" 50 0.15
SITE_PASSWORD='…' python scripts/trade.py sell "Kilowatt Case" 20 0.30 --fee 15
```

## Editing holdings by hand

```
pip install cryptography
SITE_PASSWORD='…' python scripts/data_tool.py open   # writes data.json (git-ignored)
# edit "holdings" / "sales" in data.json
SITE_PASSWORD='…' python scripts/data_tool.py seal   # writes data.enc, then commit it
```

To change the password: `OLD_PASSWORD='old' SITE_PASSWORD='new' python scripts/data_tool.py repass`,
then update the `SITE_PASSWORD` secret to match.
