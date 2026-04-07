[CmdletBinding()]
param(
    [switch]$OneFile = $true
)

$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

$entry = Join-Path $root 'JobSearchUA_parser.py'
$icon = Join-Path $root 'assets\icon.ico'

if (-not (Test-Path $entry)) { throw "Entry not found: $entry" }
if (-not (Test-Path $icon)) { throw "Icon not found: $icon" }

$args = @(
    '--noconfirm',
    '--clean',
    '--name', 'JobSearchUA_Parser',
    '--icon', $icon,
    '--add-data', "assets\beep.mp3;assets"
)

if ($OneFile) { $args += '--onefile' }
if ($OneFile) { $args += @('--runtime-tmpdir', '.\_pyi_tmp') }
$args += '--console'
$args += $entry

Write-Host "Running: pyinstaller $($args -join ' ')"
& pyinstaller @args

$exe = Join-Path $root 'dist\JobSearchUA_Parser.exe'
if (Test-Path $exe) {
    Write-Host "OK: $exe"
} else {
    Write-Host "Build finished, but EXE not found at: $exe"
    exit 1
}
