# One-time setup on your Windows PC. Run in PowerShell from the repo folder:
#   powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1
# It saves your site password for the price script, installs the Python package it needs,
# and creates a Windows scheduled task: daily at 06:47, repeating every 3 hours until 21:47,
# and catching up when the PC was off or asleep.
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }

$pw = Read-Host "Site password"
[Environment]::SetEnvironmentVariable("SITE_PASSWORD", $pw, "User")
& $py -m pip install --quiet --user cryptography

$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$repo\scripts\run_update.ps1`"" `
  -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At 06:47
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At 06:47 -RepetitionInterval (New-TimeSpan -Hours 3) -RepetitionDuration (New-TimeSpan -Hours 15)).Repetition
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "CS2 skin prices" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "Done. Running the first update now (takes a few minutes)..."
$env:SITE_PASSWORD = $pw
& "$repo\scripts\run_update.ps1"
Write-Host "Finished. See update.log in the repo folder for details."
