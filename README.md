# CS2 skin portfolio tracker

Private tracker for a CS2 skin portfolio, hosted on GitHub Pages at
**https://skins.bekasibro.my.id**.

- `index.html` is the whole site. It asks for a password and decrypts the data in the browser.
- `data.enc` holds holdings, prices, sales and value history, encrypted with AES-256-GCM.
  Without the password it is unreadable, even though the repo is public.
- `scripts/update_prices.py` pulls the lowest listing price for each item from the Steam
  Community Market, adds a row to the value history and rewrites `data.enc`. Items priced in
  the last 20 hours are skipped, so a run that Steam rate-limits is finished by the next run.
- Daily prices come from a **Claude scheduled task** (06:47 WIB). It runs
  `update_prices.py --list` to see which items need a price, fetches them from Steam,
  then runs `PRICES_FILE=fetched.json update_prices.py` and pushes `data.enc`.
  GitHub's servers get rate-limited by Steam, so the GitHub Action is manual-only, as a backup.

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
