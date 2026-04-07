[CmdletBinding()]
param(
    [switch]$OneFile = $true,
    [switch]$Console = $false
)

$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

$entry = Join-Path $root 'JobSearchUA.pyw'
$icon = Join-Path $root 'assets\icon.ico'

if (-not (Test-Path $entry)) { throw "Entry not found: $entry" }
if (-not (Test-Path $icon)) { throw "Icon not found: $icon" }

# Preflight Tkinter (required for GUI build).
# Use the python.exe that matches the pyinstaller we are invoking.
$pyInstallerExe = (Get-Command pyinstaller -ErrorAction Stop).Source
$pyRoot = Split-Path (Split-Path $pyInstallerExe -Parent) -Parent
$pyExe = Join-Path $pyRoot 'python.exe'
if (-not (Test-Path $pyExe)) { throw "python.exe not found next to pyinstaller: $pyExe" }

& $pyExe -c "import tkinter, _tkinter; print('TK_IMPORT_OK')" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'ERROR: tkinter cannot be imported in this Python installation.'
    Write-Host ("Python: $pyExe")
    exit 1
}

$args = @(
    '--noconfirm',
    '--clean',
    '--additional-hooks-dir', "tools\pyinstaller_hooks",
    '--name', 'JobSearchUA',
    '--icon', $icon,
    '--add-data', "assets\icon.ico;assets",
    '--add-data', "assets\icon.png;assets",
    '--add-data', "assets\beep.mp3;assets"
)

# Force-include tkinter and bundle Tcl/Tk scripts even if PyInstaller's tkinter probe is flaky.
$tclDir = Join-Path $pyRoot 'tcl'
$tkLib = Join-Path $tclDir 'tk8.6'

# Prefer a full Tcl library extracted into the repo (tools/tcl8.6.13/library).
$repoTclLib = Join-Path $root 'tools\tcl8.6.13\library'
if (Test-Path $repoTclLib) {
    $args += @('--add-data', ("$repoTclLib;_tcl_data"))
} else {
    $tclLib = Join-Path $tclDir 'tcl8.6'
    if (Test-Path $tclLib) {
        $args += @('--add-data', ("$tclLib;_tcl_data"))
    }
}

if (Test-Path $tkLib) {
    $args += @('--add-data', ("$tkLib;_tk_data"))
}

# Bundle tkinter python sources explicitly (PyInstaller may exclude them if it thinks Tcl/Tk is broken).
$tkinterSrc = Join-Path $pyRoot 'Lib\tkinter'
if (Test-Path $tkinterSrc) {
    $args += @('--add-data', ("$tkinterSrc;tkinter"))
}

$args += @('--hidden-import', 'tkinter', '--hidden-import', '_tkinter')

if ($OneFile) { $args += '--onefile' }
if ($OneFile) { $args += @('--runtime-tmpdir', '.\_pyi_tmp') }
if (-not $Console) { $args += '--windowed' }

$args += $entry

Write-Host "Running: pyinstaller $($args -join ' ')"
& pyinstaller @args

$exe = Join-Path $root 'dist\JobSearchUA.exe'
if (Test-Path $exe) {
    Write-Host "OK: $exe"
} else {
    Write-Host "Build finished, but EXE not found at: $exe"
    exit 1
}
