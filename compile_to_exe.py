from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _add_data_arg(src: Path, dest: str) -> list[str]:
    # PyInstaller uses OS-specific separators in --add-data:
    # - Windows: "SRC;DEST"
    # - POSIX:   "SRC:DEST"
    return ["--add-data", f"{src}{os.pathsep}{dest}"]


def _maybe_add_tk_data(args: list[str]) -> None:
    # Tkinter bundling is the #1 source of "works from Python, fails from EXE".
    # We mirror the logic used in tools/build_exe.ps1 as a Python fallback.
    root = _repo_root()

    base = Path(getattr(sys, "base_prefix", sys.prefix)).resolve()
    tcl_dir = base / "tcl"

    repo_tcl_lib = root / "tools" / "tcl8.6.13" / "library"
    if repo_tcl_lib.exists():
        args += _add_data_arg(repo_tcl_lib, "_tcl_data")
    else:
        tcl_lib = tcl_dir / "tcl8.6"
        if tcl_lib.exists():
            args += _add_data_arg(tcl_lib, "_tcl_data")

    tk_lib = tcl_dir / "tk8.6"
    if tk_lib.exists():
        args += _add_data_arg(tk_lib, "_tk_data")

    tkinter_src = base / "Lib" / "tkinter"
    if tkinter_src.exists():
        args += _add_data_arg(tkinter_src, "tkinter")

    args += ["--hidden-import", "tkinter", "--hidden-import", "_tkinter"]


def build(*, onefile: bool, console: bool) -> int:
    root = _repo_root()

    entry = root / "JobSearchUA.pyw"
    icon = root / "assets" / "icon.ico"
    hooks_dir = root / "tools" / "pyinstaller_hooks"

    if not entry.exists():
        print(f"Entry not found: {entry}", file=sys.stderr)
        return 2
    if not icon.exists():
        print(f"Icon not found: {icon}", file=sys.stderr)
        return 2

    args: list[str] = [
        "--noconfirm",
        "--clean",
        "--name",
        "JobSearchUA",
        "--icon",
        str(icon),
    ]

    if hooks_dir.exists():
        args += ["--additional-hooks-dir", str(hooks_dir)]

    args += _add_data_arg(root / "assets" / "icon.ico", "assets")
    args += _add_data_arg(root / "assets" / "icon.png", "assets")
    args += _add_data_arg(root / "assets" / "beep.mp3", "assets")

    _maybe_add_tk_data(args)

    if onefile:
        args += ["--onefile", "--runtime-tmpdir", str(root / "_pyi_tmp")]
    if console:
        args += ["--console"]
    else:
        args += ["--windowed"]

    args += [str(entry)]

    cmd = [sys.executable, "-m", "PyInstaller", *args]
    print("Running:", " ".join(cmd))
    try:
        r = subprocess.run(cmd, cwd=str(root))
    except FileNotFoundError:
        print("Python executable not found.", file=sys.stderr)
        return 1

    if r.returncode != 0:
        return r.returncode

    if onefile:
        exe = root / "dist" / "JobSearchUA.exe"
    else:
        exe = root / "dist" / "JobSearchUA" / "JobSearchUA.exe"

    if exe.exists():
        print(f"OK: {exe}")
        return 0

    print(f"Build finished, but EXE not found at: {exe}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build JobSearchUA GUI EXE via PyInstaller.")
    p.add_argument("--onefile", action="store_true", help="Build a single-file EXE (default).")
    p.add_argument("--onedir", action="store_true", help="Build a folder distribution (not onefile).")
    p.add_argument("--console", action="store_true", help="Enable console window (default: windowed GUI).")
    args = p.parse_args(argv)

    if args.onefile and args.onedir:
        print("Choose only one: --onefile or --onedir.", file=sys.stderr)
        return 2

    onefile = True
    if args.onedir:
        onefile = False
    if args.onefile:
        onefile = True

    return build(onefile=onefile, console=args.console)


if __name__ == "__main__":
    raise SystemExit(main())
