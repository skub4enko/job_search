from __future__ import annotations

import sys

from job_search.__main__ import main


def _with_default_beep(argv: list[str]) -> list[str]:
    if "--beep" in argv:
        return argv
    return [*argv, "--beep"]


if __name__ == "__main__":
    raise SystemExit(main(_with_default_beep(sys.argv[1:])))
