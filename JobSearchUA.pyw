from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _maybe_relaunch_from_venv(*, gui: bool) -> None:
    """Ensure we run with repo venv if present.

    This makes double-clicking `JobSearchUA.pyw` work even when Windows file
    association points to a global Python without dependencies installed.
    """

    # If bundled by PyInstaller or similar, don't relaunch.
    if getattr(sys, "frozen", False):
        return

    root = Path(__file__).resolve().parent

    candidates = [root / "venv" / "Scripts", root / ".venv" / "Scripts"]
    exe_name = "pythonw.exe" if gui else "python.exe"

    current = ""
    try:
        current = str(Path(sys.executable).resolve()).lower()
    except Exception:
        current = (sys.executable or "").lower()

    for scripts_dir in candidates:
        exe = scripts_dir / exe_name
        if not exe.exists():
            continue
        try:
            target = str(exe.resolve()).lower()
        except Exception:
            target = str(exe).lower()

        if current and current == target:
            return

        args = [str(exe), str(Path(__file__).resolve()), *sys.argv[1:]]
        env = dict(os.environ)
        env.setdefault("PYTHONUTF8", "1")

        if gui:
            subprocess.Popen(args, cwd=str(root), env=env)  # noqa: S603,S607
            raise SystemExit(0)

        completed = subprocess.run(args, cwd=str(root), env=env)  # noqa: S603,S607
        raise SystemExit(completed.returncode)


_maybe_relaunch_from_venv(gui=True)

from job_search.gui import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
