# Daily price update from your own PC (Windows).
# Fetches Steam prices for every item that needs one, then pushes to GitHub.
# Safe to run many times a day: items priced in the last 20 hours are skipped.
# Needs: Git, Python 3, `pip install cryptography`, and the SITE_PASSWORD user environment variable.
$ErrorActionPreference = "Continue"  # git writes progress to stderr; do not treat it as an error
Set-Location (Split-Path $PSScriptRoot -Parent)
$log = Join-Path $PSScriptRoot "..\update.log"
"=== $(Get-Date -Format s) ===" | Out-File $log -Append
git pull --rebase --quiet 2>&1 | Out-File $log -Append
if (-not $env:SITE_PASSWORD) { $env:SITE_PASSWORD = [Environment]::GetEnvironmentVariable("SITE_PASSWORD", "User") }
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
& $py scripts\update_prices.py 2>&1 | Out-File $log -Append
git add data.enc
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  git commit -m "Daily Steam prices (home PC) $(Get-Date -Format yyyy-MM-dd)" --quiet
  git push --quiet 2>&1 | Out-File $log -Append
}
