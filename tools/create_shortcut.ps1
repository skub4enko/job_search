param(
  [string]$Out = "JobSearchUA.lnk"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $root
$pyw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (!(Test-Path $pyw)) {
  throw "pythonw.exe not found: $pyw"
}

$icon = Join-Path $root "assets\icon.ico"
if (!(Test-Path $icon)) {
  $icon = Join-Path $root "assets\icon.png"
}

$wsh = New-Object -ComObject WScript.Shell
$lnkPath = Join-Path $root $Out
$sc = $wsh.CreateShortcut($lnkPath)
$sc.TargetPath = $pyw
$sc.Arguments = "-m job_search.gui"
$sc.WorkingDirectory = $root
$sc.IconLocation = $icon
$sc.WindowStyle = 7
$sc.Description = "Job Search UA"
$sc.Save()

Write-Host "OK: created $lnkPath"
