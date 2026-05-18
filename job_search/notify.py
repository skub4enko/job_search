from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def asset_path(name: str) -> Path:
    return repo_root() / "assets" / name


def _win_try_play_wav(path: Path) -> bool:
    try:
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception:
        return False


def _win_try_play_mp3_ffplay(path: Path, *, sleep_ms: int = 2500) -> bool:
    try:
        ffplay = shutil.which("ffplay")
        if not ffplay:
            return False

        startupinfo = None
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
        except Exception:
            startupinfo = None

        r = subprocess.run(
            [
                ffplay,
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                "-volume",
                "100",
                str(path.resolve()),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            check=False,
            timeout=max(3.0, sleep_ms / 1000.0 + 2.0),
        )
        return r.returncode == 0
    except Exception:
        return False


def _win_try_play_mp3_wmplayer(path: Path, *, sleep_ms: int = 2000) -> bool:
    try:
        p = path.resolve()
        p_escaped = str(p).replace("'", "''")
        ps = (
            "try {"
            "  $ErrorActionPreference='Stop';"
            "  $wmp=New-Object -ComObject WMPlayer.OCX;"
            "  $wmp.settings.volume=100;"
            f"  $wmp.URL='{p_escaped}';"
            "  $wmp.controls.play();"
            f"  Start-Sleep -Milliseconds {int(sleep_ms)};"
            "  $wmp.close();"
            "  exit 0;"
            "} catch { exit 1 }"
        )

        CREATE_NO_WINDOW = 0x08000000
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            check=False,
            timeout=max(3.0, sleep_ms / 1000.0 + 1.0),
        )
        return r.returncode == 0
    except Exception:
        return False


def _win_try_play_mp3_wpf(path: Path, *, sleep_ms: int = 2000) -> bool:
    try:
        uri = path.resolve().as_uri()
        uri_escaped = uri.replace("'", "''")
        ps = (
            "try {"
            "  $ErrorActionPreference='Stop';"
            "  Add-Type -AssemblyName presentationCore;"
            "  $player=New-Object System.Windows.Media.MediaPlayer;"
            f"  $player.Open([System.Uri]'{uri_escaped}');"
            "  $player.Volume=1.0;"
            "  $player.Play();"
            f"  Start-Sleep -Milliseconds {int(sleep_ms)};"
            "  $player.Close();"
            "  exit 0;"
            "} catch { exit 1 }"
        )

        CREATE_NO_WINDOW = 0x08000000
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            check=False,
            timeout=max(3.0, sleep_ms / 1000.0 + 1.0),
        )
        return r.returncode == 0
    except Exception:
        return False


def _fallback_beep() -> None:
    if sys.platform.startswith("win"):
        try:
            import winsound

            try:
                winsound.Beep(880, 220)  # type: ignore[attr-defined]
                return
            except Exception:
                pass

            winsound.MessageBeep()  # type: ignore[attr-defined]
            return
        except Exception:
            return

    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        return


def play_sound(path: Path | str | None) -> None:
    try:
        p = Path(path) if path else None
        if p is None or not p.exists():
            _fallback_beep()
            return

        if not sys.platform.startswith("win"):
            _fallback_beep()
            return

        ext = p.suffix.lower()
        if ext == ".wav":
            if _win_try_play_wav(p):
                return
            _fallback_beep()
            return

        if _win_try_play_mp3_ffplay(p):
            return
        if _win_try_play_mp3_wmplayer(p):
            return
        if _win_try_play_mp3_wpf(p):
            return

        _fallback_beep()
    except Exception:
        return


def play_sound_async(path: Path | str | None) -> None:
    threading.Thread(target=lambda: play_sound(path), daemon=True).start()


def diagnose_sound(path: Path | str | None) -> dict:
    """Return diagnostics explaining why MP3 may not play on this system."""
    try:
        p = Path(path) if path else None
        info: dict = {
            "platform": sys.platform,
            "path": str(p) if p else None,
            "exists": bool(p and p.exists()),
            "ext": (p.suffix.lower() if p else None),
            "ffplay_in_path": bool(shutil.which("ffplay")),
        }

        if not sys.platform.startswith("win"):
            info["reason"] = "Non-Windows: only fallback bell is available in this project."
            return info

        try:
            import winreg

            winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "WMPlayer.OCX")
            info["wmplayer_com"] = True
        except Exception:
            info["wmplayer_com"] = False

        info["note"] = (
            "If WMPlayer COM is missing, Windows Media Player / Media Features may be disabled/absent (e.g. Windows N). "
            "WPF MediaPlayer also depends on system codecs; MP3 can be silent if Media Foundation components are missing. "
            "Install Media Feature Pack / enable 'Media Features', or install ffmpeg (ffplay) and keep ffplay in PATH, "
            "or use a WAV file."
        )
        return info
    except Exception as e:
        return {"error": str(e)}

