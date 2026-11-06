# CS2 skin portfolio tracker

Password-protected portfolio site at **https://skins.bekasibro.my.id**, served by GitHub Pages.

| File | What it is |
|---|---|
| `index.html` | The whole site. Decrypts `data.enc` in the browser with the password. |
| `data.enc` | Holdings, prices, sales and value history, AES-256-GCM encrypted. |
| `items.txt` | Item names only. |
| `incoming/prices.json` | Optional manual prices for items the feed doesn't cover. |
| `scripts/apply_prices.py` | Merges `incoming/prices.json` into `data.enc`, and flags differences with the public Steam inventory. |
| `scripts/trade.py` | Record a buy or sell (updates holdings, sales and `items.txt`). |
| `scripts/data_tool.py` | Open, edit and re-seal `data.enc` by hand, or change the password. |
| `scripts/crypto_box.py` | Encryption shared by both scripts (browser-compatible). |
| `.github/workflows/apply-prices.yml` | Runs `apply_prices.py` when new prices are pushed. |
| `android/` | Small Android app that opens the site full-screen. |
| `.github/workflows/android.yml` | Builds the app and publishes it as `download/cs2-portfolio.apk`. |

## How prices update

The **Apply prices** workflow runs every day at 06:47 WIB (retry at 12:17 WIB). It:
- downloads Steam prices for every item in one request from the public
  [CSGO Trader price feed](https://prices.csgotrader.app/latest/steam.json): the average
  Steam sale price over the last 24 hours (falling back to 7, 30 or 90 days);
- adds Skinport's lowest listing and the USD→IDR rate;
- checks the public Steam inventory (often rate-limited by Steam);
- merges everything into `data.enc` with the `SITE_PASSWORD` repository secret.

`incoming/prices.json` can hold manual prices for items the feed lacks.

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
