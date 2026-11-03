# CS2 skin portfolio tracker

Private tracker for a CS2 skin portfolio, hosted on GitHub Pages at
**https://skins.bekasibro.my.id**.

- `index.html` is the whole site. It asks for a password and decrypts the data in the browser.
- `data.enc` holds holdings, prices, sales and value history, encrypted with AES-256-GCM.
  Without the password it is unreadable, even though the repo is public.
- `scripts/update_prices.py` pulls the lowest listing price for each item from the Steam
  Community Market, adds a row to the value history and rewrites `data.enc`. Items priced in
  the last 20 hours are skipped, so a run that Steam rate-limits is finished by the next run.
- Daily prices come from a **Claude scheduled task** (06:47 and 13:47 WIB). It reads
  `items.txt` (item names only), looks each one up with Steam's market search, and pushes
  plain prices to `incoming/prices.json`. It never sees the password.
- `.github/workflows/apply-prices.yml` runs on that push. It merges the prices into
  `data.enc` using the `SITE_PASSWORD` secret and refreshes `items.txt`. Items without a new
  price keep their previous one and show in orange on the site.
- `update-prices.yml` (direct Steam fetch from GitHub) is manual-only, because Steam
  rate-limits GitHub's servers.

## One-time setup

1. **Secret:** repo Settings → Secrets and variables → Actions → New repository secret.
   Name `SITE_PASSWORD`, value = the site password.
2. **Pages:** Settings → Pages → Source "Deploy from a branch" → branch `main`, folder `/ (root)`.
   Custom domain: `skins.bekasibro.my.id`, then tick "Enforce HTTPS" once it is offered.
3. **DNS** (indo.domains → bekasibro.my.id → DNS): add a `CNAME` record,
   host `skins`, value `superxplodz.github.io`.

## Editing holdings by hand

```
pip install cryptography
SITE_PASSWORD='…' python scripts/data_tool.py open    # writes data.json (never commit it)
# edit data.json
SITE_PASSWORD='…' python scripts/data_tool.py seal    # writes data.enc
```

Change the password: `OLD_PASSWORD='old' SITE_PASSWORD='new' python scripts/data_tool.py repass`,
then update the `SITE_PASSWORD` secret to match.
