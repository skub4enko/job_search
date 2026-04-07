from __future__ import annotations

import json
import sys
import os
import subprocess
import shutil
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

from job_search.keys import load_api_keys
from job_search.runner import run
from job_search.server import start_server
from job_search.notify import asset_path, play_sound_async
from job_search.store import load_payload, merge_payload


def _try_set_ui_fonts() -> None:
    # Ensure all UI languages render correctly on Windows (Segoe UI supports Cyrillic/Latin).
    try:
        default = tkfont.nametofont("TkDefaultFont")
        default.configure(family="Segoe UI", size=9)
        for name in [
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkSmallCaptionFont",
            "TkIconFont",
            "TkTooltipFont",
        ]:
            try:
                tkfont.nametofont(name).configure(family="Segoe UI", size=9)
            except Exception:
                pass
        try:
            tkfont.nametofont("TkFixedFont").configure(family="Consolas", size=9)
        except Exception:
            pass
    except Exception:
        return


def _now_kyiv() -> datetime:
    if ZoneInfo is None:
        return datetime.now()
    try:
        return datetime.now(ZoneInfo("Europe/Kyiv"))
    except Exception:
        return datetime.now()


def _expand_out_template(template: str) -> Path:
    dt = _now_kyiv()
    s = template
    s = s.replace("{date}", dt.strftime("%Y-%m-%d"))
    s = s.replace("{datetime}", dt.strftime("%Y-%m-%d_%H-%M"))
    return Path(s)


def _parse_queries(text: str) -> list[str]:
    parts = [p.strip() for p in text.replace(";", ",").split(",")]
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if not p:
            continue
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out

def _parse_locations(text: str) -> list[str]:
    """Parse a comma/semicolon-separated list of locations (cities).

    Uses the same normalization/dedup rules as queries.
    """
    return _parse_queries(text)

# --- UI translations (labels/buttons/dialogs only; logs remain English) ---
TRANSLATIONS: dict[str, dict[str, str]] = {
    "uk": {
        "Job Search UA": "\u041f\u043e\u0448\u0443\u043a \u0440\u043e\u0431\u043e\u0442\u0438 UA",
        "Queries (comma-separated):": "\u0417\u0430\u043f\u0438\u0442\u0438 (\u0447\u0435\u0440\u0435\u0437 \u043a\u043e\u043c\u0443):",
        "remote only": "\u043b\u0438\u0448\u0435 \u0432\u0456\u0434\u0434\u0430\u043b\u0435\u043d\u043e",
        "verbose": "\u0434\u0435\u0442\u0430\u043b\u044c\u043d\u043e",
        "dark mode": "\u0442\u0435\u043c\u043d\u0430 \u0442\u0435\u043c\u0430",
        "use cache": "\u0432\u0438\u043a\u043e\u0440\u0438\u0441\u0442\u043e\u0432\u0443\u0432\u0430\u0442\u0438 \u043a\u0435\u0448",
        "Clear cache": "\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u0438 \u043a\u0435\u0448",
        "Language:": "\u041c\u043e\u0432\u0430:",
        "Sources:": "\u0414\u0436\u0435\u0440\u0435\u043b\u0430:",
        "Location:": "\u041b\u043e\u043a\u0430\u0446\u0456\u044f:",
        "Locations (comma-separated):": "Локації (через кому):",
        "Max pages:": "\u0421\u0442\u043e\u0440\u0456\u043d\u043e\u043a:",
        "Output JSON (template):": "JSON \u0444\u0430\u0439\u043b (\u0448\u0430\u0431\u043b\u043e\u043d):",
        "State file:": "\u0424\u0430\u0439\u043b \u0441\u0442\u0430\u043d\u0443:",
        "Search / update JSON": "\u041f\u043e\u0448\u0443\u043a / \u043e\u043d\u043e\u0432\u0438\u0442\u0438 JSON",
        "Pause": "\u041f\u0430\u0443\u0437\u0430",
        "Resume": "\u041f\u0440\u043e\u0434\u043e\u0432\u0436\u0438\u0442\u0438",
        "Stop": "\u0417\u0443\u043f\u0438\u043d\u0438\u0442\u0438",
        "View in browser": "\u041f\u0435\u0440\u0435\u0433\u043b\u044f\u043d\u0443\u0442\u0438 \u0432 \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0456",
        "Open JSON file": "\u0412\u0456\u0434\u043a\u0440\u0438\u0442\u0438 JSON \u0444\u0430\u0439\u043b",
        "Ready": "\u0413\u043e\u0442\u043e\u0432\u043e",
        "Running...": "\u041f\u0440\u0430\u0446\u044e\u044e...",
        "Paused": "\u041f\u0430\u0443\u0437\u0430",
        "Stopping...": "\u0417\u0443\u043f\u0438\u043d\u043a\u0430...",
        "Error": "\u041f\u043e\u043c\u0438\u043b\u043a\u0430",
        "Busy": "\u0417\u0430\u0439\u043d\u044f\u0442\u043e",
        "Cache": "\u041a\u0435\u0448",
        "Please enter at least one query": "\u0412\u043a\u0430\u0436\u0456\u0442\u044c \u0445\u043e\u0447\u0430 \u0431 \u043e\u0434\u0438\u043d \u0437\u0430\u043f\u0438\u0442",
        "No sources selected": "\u041d\u0435 \u0432\u0438\u0431\u0440\u0430\u043d\u043e \u0436\u043e\u0434\u043d\u043e\u0433\u043e \u0434\u0436\u0435\u0440\u0435\u043b\u0430",
        "Stop parsing before clearing cache.": "\u0417\u0443\u043f\u0438\u043d\u0456\u0442\u044c \u043f\u0430\u0440\u0441\u0438\u043d\u0433 \u043f\u0435\u0440\u0435\u0434 \u043e\u0447\u0438\u0449\u0435\u043d\u043d\u044f\u043c \u043a\u0435\u0448\u0443.",
        "Cache folder not found:": "\u041f\u0430\u043f\u043a\u0443 \u043a\u0435\u0448\u0443 \u043d\u0435 \u0437\u043d\u0430\u0439\u0434\u0435\u043d\u043e:",
        "Delete cache folder?": "\u0412\u0438\u0434\u0430\u043b\u0438\u0442\u0438 \u043f\u0430\u043f\u043a\u0443 \u043a\u0435\u0448\u0443?",
        "Failed to clear cache:": "\u041d\u0435 \u0432\u0434\u0430\u043b\u043e\u0441\u044f \u043e\u0447\u0438\u0441\u0442\u0438\u0442\u0438 \u043a\u0435\u0448:",
        "Failed to start server:": "\u041d\u0435 \u0432\u0434\u0430\u043b\u043e\u0441\u044f \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0438 \u0441\u0435\u0440\u0432\u0435\u0440:",
        "File": "\u0424\u0430\u0439\u043b",
        "File not found:": "\u0424\u0430\u0439\u043b \u043d\u0435 \u0437\u043d\u0430\u0439\u0434\u0435\u043d\u043e:",
        "Done:": "\u0413\u043e\u0442\u043e\u0432\u043e:",
    },
    "pl": {
        "Job Search UA": "Wyszukiwanie ofert UA",
        "Queries (comma-separated):": "Zapytania (oddzielone przecinkami):",
        "remote only": "tylko zdalnie",
        "verbose": "szczeg\u00f3\u0142owo",
        "dark mode": "tryb ciemny",
        "use cache": "u\u017cyj cache",
        "Clear cache": "Wyczy\u015b\u0107 cache",
        "Language:": "J\u0119zyk:",
        "Sources:": "\u0179r\u00f3d\u0142a:",
        "Location:": "Lokalizacja:",
        "Locations (comma-separated):": "Lokalizacje (oddzielone przecinkami):",
        "Max pages:": "Maks. stron:",
        "Output JSON (template):": "Wyj\u015bciowy JSON (szablon):",
        "State file:": "Plik stanu:",
        "Search / update JSON": "Szukaj / aktualizuj JSON",
        "Pause": "Pauza",
        "Resume": "Wzn\u00f3w",
        "Stop": "Zatrzymaj",
        "View in browser": "Otw\u00f3rz w przegl\u0105darce",
        "Open JSON file": "Otw\u00f3rz plik JSON",
        "Ready": "Gotowe",
        "Running...": "Praca...",
        "Paused": "Wstrzymano",
        "Stopping...": "Zatrzymywanie...",
        "Error": "B\u0142\u0105d",
        "Busy": "Zaj\u0119te",
        "Cache": "Cache",
        "Please enter at least one query": "Wpisz co najmniej jedno zapytanie",
        "No sources selected": "Nie wybrano \u017ar\u00f3de\u0142",
        "Stop parsing before clearing cache.": "Zatrzymaj wyszukiwanie przed czyszczeniem cache.",
        "Cache folder not found:": "Nie znaleziono folderu cache:",
        "Delete cache folder?": "Usun\u0105\u0107 folder cache?",
        "Failed to clear cache:": "Nie uda\u0142o si\u0119 wyczy\u015bci\u0107 cache:",
        "Failed to start server:": "Nie uda\u0142o si\u0119 uruchomi\u0107 serwera:",
        "File": "Plik",
        "File not found:": "Nie znaleziono pliku:",
        "Done:": "Gotowe:",
    },
    "de": {
        "Job Search UA": "Jobsuche UA",
        "Queries (comma-separated):": "Suchbegriffe (durch Komma getrennt):",
        "remote only": "nur remote",
        "verbose": "ausf\u00fchrlich",
        "dark mode": "dunkles Design",
        "use cache": "Cache verwenden",
        "Clear cache": "Cache leeren",
        "Language:": "Sprache:",
        "Sources:": "Quellen:",
        "Location:": "Ort:",
        "Locations (comma-separated):": "Orte (durch Komma getrennt):",
        "Max pages:": "Max. Seiten:",
        "Output JSON (template):": "JSON-Ausgabe (Vorlage):",
        "State file:": "Statusdatei:",
        "Search / update JSON": "Suchen / JSON aktualisieren",
        "Pause": "Pause",
        "Resume": "Fortsetzen",
        "Stop": "Stopp",
        "View in browser": "Im Browser ansehen",
        "Open JSON file": "JSON-Datei \u00f6ffnen",
        "Ready": "Bereit",
        "Running...": "L\u00e4uft...",
        "Paused": "Pausiert",
        "Stopping...": "Wird beendet...",
        "Error": "Fehler",
        "Busy": "Besch\u00e4ftigt",
        "Cache": "Cache",
        "Please enter at least one query": "Bitte mindestens einen Suchbegriff eingeben",
        "No sources selected": "Keine Quellen ausgew\u00e4hlt",
        "Stop parsing before clearing cache.": "Bitte Vorgang stoppen, bevor der Cache geleert wird.",
        "Cache folder not found:": "Cache-Ordner nicht gefunden:",
        "Delete cache folder?": "Cache-Ordner l\u00f6schen?",
        "Failed to clear cache:": "Cache konnte nicht geleert werden:",
        "Failed to start server:": "Server konnte nicht gestartet werden:",
        "File": "Datei",
        "File not found:": "Datei nicht gefunden:",
        "Done:": "Fertig:",
    },
}

TEXT_TO_EN: dict[str, str] = {}
for _lang, _pairs in TRANSLATIONS.items():
    for _en, _tr in _pairs.items():
        TEXT_TO_EN[_en] = _en
        TEXT_TO_EN[_tr] = _en


def _win_set_app_user_model_id(app_id: str) -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)  # type: ignore[attr-defined]
    except Exception:
        return


def _win_ensure_ico_from_png(png_path: Path, ico_path: Path) -> None:
    if not sys.platform.startswith("win"):
        return
    if ico_path.exists():
        return
    if not png_path.exists():
        return

    try:
        # Use PowerShell + System.Drawing to convert PNG -> ICO once.
        ps = (
            "$ErrorActionPreference='SilentlyContinue';"
            "Add-Type -AssemblyName System.Drawing;"
            f"$png='{str(png_path).replace("'", "''")}';"
            f"$ico='{str(ico_path).replace("'", "''")}';"
            "$bmp=[System.Drawing.Bitmap]::FromFile($png);"
            "$icon=[System.Drawing.Icon]::FromHandle($bmp.GetHicon());"
            "$fs=New-Object System.IO.FileStream($ico,[System.IO.FileMode]::Create);"
            "$icon.Save($fs);$fs.Close();"
            "$bmp.Dispose();$icon.Dispose();"
        )
        CREATE_NO_WINDOW = 0x08000000
        import subprocess

        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    except Exception:
        return


def _win_set_window_icons(root: tk.Tk, ico_path: Path) -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = root.winfo_id()
        if not hwnd:
            return

        # Ensure the window is created.
        try:
            root.update_idletasks()
        except Exception:
            pass

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        LR_DEFAULTSIZE = 0x0040
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        user32.LoadImageW.restype = wintypes.HANDLE
        hicon = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if not hicon:
            return

        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
        # Keep handle referenced.
        root._win_hicon = hicon  # type: ignore[attr-defined]
    except Exception:
        return
def _try_set_app_icon(root: tk.Tk) -> None:
    icon_png = asset_path("icon.png")
    icon_ico = asset_path("icon.ico").resolve()

    # 1) Windows taskbar/title icon prefers .ico
    if sys.platform.startswith("win") and icon_ico.exists():
        try:
            root.iconbitmap(default=str(icon_ico))
            _win_set_window_icons(root, icon_ico)
            try:
                root.after(50, lambda: _win_set_window_icons(root, icon_ico))
            except Exception:
                pass
        except Exception as e:
            try:
                print(f"[icon] iconbitmap failed: {e}", file=sys.stderr)
            except Exception:
                pass

    # 2) Also set PhotoImage (works cross-platform, affects title bar in many cases)
    if icon_png.exists():
        try:
            img = tk.PhotoImage(file=str(icon_png))
            root.iconphoto(True, img)
            root._app_icon_img = img  # type: ignore[attr-defined]
        except Exception as e:
            try:
                print(f"[icon] iconphoto failed: {e}", file=sys.stderr)
            except Exception:
                pass



class App:
    def _t(self, s: str) -> str:
        lang = getattr(self, "_lang", "en")
        if lang == "en":
            return s
        return TRANSLATIONS.get(lang, {}).get(s, s)

    def _apply_language(self) -> None:
        # Translate existing widget texts using English as a canonical key.
        lang = getattr(self, "_lang", "en")

        def tr_text(current: str) -> str | None:
            en = TEXT_TO_EN.get(current)
            if not en:
                return None
            if lang == "en":
                return en
            return TRANSLATIONS.get(lang, {}).get(en, en)

        def walk(w: tk.Misc) -> None:
            for ch in w.winfo_children():
                try:
                    t = ch.cget("text")
                    nt = tr_text(t)
                    if nt is not None and nt != t:
                        ch.config(text=nt)
                except Exception:
                    pass
                try:
                    walk(ch)
                except Exception:
                    pass

        try:
            title = self.root.title()
            nt = tr_text(title)
            if nt is not None and nt != title:
                self.root.title(nt)
        except Exception:
            pass

        walk(self.root)

    def __init__(self, root: tk.Tk):
        self.root = root
        self._lang = "en"
        self.root.title("Job Search UA")
        self.root.geometry("900x560")

        self._server = None
        self._cancel_event: threading.Event | None = None
        self._pause_event: threading.Event | None = None
        self._query_label = ""
        self._last_out: Path | None = None
        self.cache_dir = Path(__file__).resolve().parents[1] / ".cache_http"

        frm = ttk.Frame(root, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        row0 = ttk.Frame(frm)
        row0.pack(fill=tk.X)

        ttk.Label(row0, text="Queries (comma-separated):").pack(side=tk.LEFT)
        self.q_var = tk.StringVar(value="Python developer")
        self.location_var = tk.StringVar(value="")
        ttk.Entry(row0, textvariable=self.q_var, width=55).pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        self.remote_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(row0, text="remote only", variable=self.remote_only).pack(side=tk.LEFT)

        self.verbose = tk.BooleanVar(value=False)
        ttk.Checkbutton(row0, text="verbose", variable=self.verbose).pack(side=tk.LEFT, padx=8)

        self.dark_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(row0, text="dark mode", variable=self.dark_mode, command=self._apply_theme).pack(
            side=tk.LEFT
        )

        row0b = ttk.Frame(frm)
        row0b.pack(fill=tk.X, pady=(6, 0))

        ttk.Label(row0b, text="Language:").pack(side=tk.LEFT)
        self._lang_map = {"English": "en", "\u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430": "uk", "Polski": "pl", "Deutsch": "de"}
        self.lang_combo = ttk.Combobox(row0b, values=list(self._lang_map.keys()), state="readonly", width=14)
        self.lang_combo.set("English")
        self.lang_combo.pack(side=tk.LEFT, padx=6)

        ttk.Label(row0b, text="Locations (comma-separated):").pack(side=tk.LEFT, padx=(14, 0))
        ttk.Entry(row0b, textvariable=self.location_var, width=30).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)

        def _on_lang(_e=None):
            label = self.lang_combo.get()
            self._lang = self._lang_map.get(label, "en")
            self._apply_language()

        self.lang_combo.bind("<<ComboboxSelected>>", _on_lang)

        row_sources = ttk.Frame(frm)
        row_sources.pack(fill=tk.X, pady=(6, 0))

        ttk.Label(row_sources, text="Sources:").pack(side=tk.LEFT)
        self.src_vars = {
            "workua": tk.BooleanVar(value=False),
            "rabotaua": tk.BooleanVar(value=False),
            "dou": tk.BooleanVar(value=False),
            "jobsua": tk.BooleanVar(value=False),
            "olxua": tk.BooleanVar(value=False),
            "grcua": tk.BooleanVar(value=False),
            "talentua": tk.BooleanVar(value=False),
            "jooble": tk.BooleanVar(value=False),
            "indeed": tk.BooleanVar(value=False),
            "trudnet": tk.BooleanVar(value=False),
        }
        labels = {
            "workua": "Work.ua",
            "rabotaua": "Robota.ua",
            "dou": "DOU",
            "jobsua": "Jobs.ua",
            "olxua": "OLX (Jobs)",
            "grcua": "GRC",
            "talentua": "Talent.UA",
            "jooble": "Jooble",
            "indeed": "Indeed (API)",
            "trudnet": "Trud.net",
        }
        for key in ["workua", "rabotaua", "dou", "jobsua", "olxua", "trudnet", "grcua", "talentua", "jooble", "indeed"]:
            ttk.Checkbutton(row_sources, text=labels[key], variable=self.src_vars[key]).pack(side=tk.LEFT, padx=6)

        row1 = ttk.Frame(frm)
        row1.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(row1, text="Max pages:").pack(side=tk.LEFT)
        self.max_pages_var = tk.StringVar(value="3")
        ttk.Entry(row1, textvariable=self.max_pages_var, width=6).pack(side=tk.LEFT, padx=8)

        ttk.Label(row1, text="Output JSON (template):").pack(side=tk.LEFT)
        self.out_var = tk.StringVar(value="results/output_{date}.json")
        ttk.Entry(row1, textvariable=self.out_var, width=28).pack(side=tk.LEFT, padx=8)

        ttk.Label(row1, text="State file:").pack(side=tk.LEFT)
        self.state_var = tk.StringVar(value="results/jobs_state.json")
        ttk.Entry(row1, textvariable=self.state_var, width=22).pack(side=tk.LEFT, padx=8)

        self.use_cache_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="use cache", variable=self.use_cache_var).pack(side=tk.LEFT, padx=8)

        row2 = ttk.Frame(frm)
        row2.pack(fill=tk.X, pady=(12, 0))

        self.btn_run = ttk.Button(row2, text="Search / update JSON", command=self.on_run)
        self.btn_run.pack(side=tk.LEFT)

        self.btn_pause = ttk.Button(row2, text="Pause", command=self.on_pause, state=tk.DISABLED)
        self.btn_pause.pack(side=tk.LEFT, padx=8)

        self.btn_stop = ttk.Button(row2, text="Stop", command=self.on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT)

        self.btn_view = ttk.Button(row2, text="View in browser", command=self.on_view)
        self.btn_view.pack(side=tk.LEFT, padx=8)

        self.btn_open_file = ttk.Button(row2, text="Open JSON file", command=self.on_open_file)
        self.btn_open_file.pack(side=tk.LEFT)

        self.btn_clear_cache = ttk.Button(row2, text="Clear cache", command=self.on_clear_cache)
        self.btn_clear_cache.pack(side=tk.LEFT, padx=8)

        self.status = tk.StringVar(value=self._t("Ready"))
        self.pbar = ttk.Progressbar(row2, mode="indeterminate", length=160)
        self.pbar.pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Label(row2, textvariable=self.status).pack(side=tk.RIGHT)

        self.log = tk.Text(frm, height=20)
        self.log.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        try:
            ipng = asset_path("icon.png")
            iico = asset_path("icon.ico")
            self._append_log(f"Icon: png={'OK' if ipng.exists() else 'missing'} ico={'OK' if iico.exists() else 'missing'}")
        except Exception:
            pass

        self._set_buttons(enabled=True)
        self._apply_theme()
        self._load_api_keys()

    def _set_buttons(self, *, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.btn_run.config(state=state)
        self.btn_view.config(state=state)
        self.btn_open_file.config(state=state)
        self.btn_clear_cache.config(state=state)

    def _append_log(self, text: str) -> None:
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)

    def _apply_theme(self) -> None:
        # Tkinter doesn't have a true native dark mode; we approximate via ttk styles + Text colors.
        style = ttk.Style()
        dark = bool(self.dark_mode.get())

        if dark:
            try:
                style.theme_use("clam")
            except Exception:
                pass

            bg = "#1e1e1e"
            fg = "#e6e6e6"
            field_bg = "#2b2b2b"
            btn_bg = "#2d2d2d"
            btn_active = "#3a3a3a"

            style.configure(".", background=bg, foreground=fg)
            style.configure("TFrame", background=bg)
            style.configure("TLabel", background=bg, foreground=fg)
            style.configure("TCheckbutton", background=bg, foreground=fg)
            style.configure("TButton", background=btn_bg, foreground=fg)
            style.map("TButton", background=[("active", btn_active)])
            style.configure("TEntry", fieldbackground=field_bg, foreground=fg)

            self.root.configure(bg=bg)
            self.log.configure(bg="white", fg="black", insertbackground="black")
            return

        # Light / default
        try:
            if "vista" in style.theme_names():
                style.theme_use("vista")
            elif "xpnative" in style.theme_names():
                style.theme_use("xpnative")
        except Exception:
            pass
        self.root.configure(bg="")
        self.log.configure(bg="#111111", fg="#e6e6e6", insertbackground="#e6e6e6")

    def _load_api_keys(self) -> None:
        # Load API keys from a local file, but avoid bundling secrets into the EXE.
        #
        # - Source run: reads `assets/api.txt` (if present).
        # - Frozen/EXE: reads `api.txt` next to the EXE (if present).
        #
        # Users can also set env vars directly: JOOBLE_API_KEY / SCRAPEOPS_API_KEY.
        try:
            need_jooble = not os.getenv("JOOBLE_API_KEY")
            need_scrapeops = not os.getenv("SCRAPEOPS_API_KEY")
            if not (need_jooble or need_scrapeops):
                return

            if getattr(sys, "frozen", False):
                api_path = Path(sys.executable).resolve().parent / "api.txt"
                label = "api.txt"
            else:
                api_path = asset_path("api.txt")
                label = "assets/api.txt"

            keys = load_api_keys(api_path)

            if keys.jooble and need_jooble:
                os.environ["JOOBLE_API_KEY"] = keys.jooble
            if keys.scrapeops and need_scrapeops:
                os.environ["SCRAPEOPS_API_KEY"] = keys.scrapeops

            if keys.jooble:
                self._append_log(f"Keys: Jooble key loaded from {label}")
            if keys.scrapeops:
                self._append_log(f"Keys: ScrapeOps key loaded from {label}")
        except Exception as e:
            self._append_log(f"Keys: failed to load api.txt: {e}")

    def on_run(self) -> None:
        queries = _parse_queries(self.q_var.get())
        if not queries:
            messagebox.showerror(self._t("Error"), self._t("Please enter at least one query"))
            return

        sources = [k for k, v in self.src_vars.items() if bool(v.get())]
        if not sources:
            messagebox.showerror(self._t("Error"), self._t("No sources selected"))
            return

        out_template = self.out_var.get().strip() or "results/output_{date}.json"
        out_path = _expand_out_template(out_template)
        state_path = Path(self.state_var.get().strip() or "results/jobs_state.json")
        locations = _parse_locations(self.location_var.get())
        if not locations:
            locations = [""]
        try:
            max_pages = int((self.max_pages_var.get() or "").strip() or "3")
        except Exception:
            max_pages = 3
        max_pages = max(1, min(50, max_pages))


        self._set_buttons(enabled=False)
        self.status.set(self._t("Running..."))
        try:
            self.pbar.start(12)
        except Exception:
            pass
        self._append_log(f"Run: queries={queries} locations={locations!r} sources={sources} max_pages={max_pages} out={out_path} state={state_path}")

        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self.btn_pause.config(state=tk.NORMAL, text=self._t("Pause"))
        self.btn_stop.config(state=tk.NORMAL)
        started = time.perf_counter()

        def worker() -> None:
            try:
                verbose = bool(self.verbose.get())

                def log_fn(msg: str) -> None:
                    def apply() -> None:
                        # Special progress messages from runner (GUI-only)
                        if msg.startswith("[progress] "):
                            st = msg[len("[progress] "):].strip()
                            # Pretty-name sources in the status bar.
                            pretty = {
                                "workua": "Work.ua",
                                "rabotaua": "Robota.ua",
                                "dou": "DOU",
                                "jooble": "Jooble",
                                "indeed": "Indeed",
                                "jobsua": "Jobs.ua",
                                "talentua": "Talent.UA",
                                "grcua": "GRC",
                                "olxua": "OLX",
                            }
                            if ":" in st:
                                head, rest = st.split(":", 1)
                                head = head.strip()
                                if head in pretty:
                                    st = pretty[head] + ":" + rest
                            if self._query_label:
                                self.status.set(f"{self._query_label} - {st}")
                            else:
                                self.status.set(st)
                        self._append_log(msg)

                    self.root.after(0, apply)

                cancel_ev = self._cancel_event
                pause_ev = self._pause_event


                fresh_jobs = []
                total_q = len(queries)
                total_l = len(locations) if locations else 1
                location_terms = [c for c in locations if c]
                for qi, q in enumerate(queries, start=1):
                    if cancel_ev is not None and cancel_ev.is_set():
                        break
                    for li, city in enumerate(locations, start=1):
                        if cancel_ev is not None and cancel_ev.is_set():
                            break
                        label = f"Query {qi}/{total_q}"
                        if total_l > 1:
                            if city:
                                label += f", Location {li}/{total_l}: {city}"
                            else:
                                label += f", Location {li}/{total_l}: (any)"
                        elif city:
                            label += f", Location: {city}"
                        self.root.after(0, lambda label=label: setattr(self, "_query_label", label))
                        log_fn(
                            f"[progress] query: {qi}/{total_q} {q!r} city={city!r}" if city else f"[progress] query: {qi}/{total_q} {q!r}"
                        )
                        fresh_jobs.extend(
                            run(
                                query=q,
                                city=city,
                                remote_only=bool(self.remote_only.get()),
                                sources=sources,
                                max_pages=max_pages,
                                limit=200,
                                cache_dir=self.cache_dir,
                                use_cache=bool(self.use_cache_var.get()),
                                timeout_s=25.0,
                                concurrency=10,
                                verbose=verbose,
                                log_fn=log_fn,
                                pause_event=pause_ev,
                                cancel_event=cancel_ev,
                            )
                        )

                # Some providers still return other cities even when city=... was requested.
                # Enforce a strict post-filter when the user entered explicit locations.
                if location_terms:
                    terms_cf = [t.casefold() for t in location_terms]
                    def _loc_ok(loc: str) -> bool:
                        ll = (loc or "").casefold()
                        return any(t in ll for t in terms_cf)
                    fresh_jobs = [j for j in fresh_jobs if _loc_ok(getattr(j, "location", ""))]

                fresh_payload = [asdict(j) for j in fresh_jobs]
                existing = load_payload(state_path)
                merged = merge_payload(existing, fresh_payload)

                state_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
                out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

                active = sum(1 for r in merged if isinstance(r, dict) and r.get("is_active"))
                self._last_out = out_path

                self.root.after(0, lambda: self._append_log(f"OK: records={len(merged)} active={active}"))
                self.root.after(0, lambda: self.status.set(f"{self._t("Done:")} {len(merged)} (active={active})"))
                self.root.after(0, lambda: play_sound_async(asset_path("beep.mp3")))
                self.root.after(0, lambda: self._append_log("Sound: play assets/beep.mp3"))
            except Exception as e:
                self.root.after(0, lambda: self._append_log(f"ERROR: {e}"))
                self.root.after(0, lambda: messagebox.showerror(self._t("Error"), str(e)))
                self.root.after(0, lambda: self.status.set(self._t("Error")))
            finally:
                elapsed = time.perf_counter() - started
                def fmt(sec: float) -> str:
                    s = int(sec)
                    return f"{s//60:02d}:{s%60:02d}"
                self.root.after(0, lambda: self._append_log(f"Elapsed: {fmt(elapsed)}"))
                self._cancel_event = None
                self._pause_event = None
                self.root.after(0, lambda: self.btn_pause.config(state=tk.DISABLED, text=self._t("Pause")))
                self.root.after(0, lambda: self.btn_stop.config(state=tk.DISABLED))
                self.root.after(0, lambda: getattr(self, "pbar", None) and self.pbar.stop())
                self.root.after(0, lambda: self._set_buttons(enabled=True))

        threading.Thread(target=worker, daemon=True).start()


    def on_clear_cache(self) -> None:
        # Only allow when idle.
        if self._cancel_event is not None:
            messagebox.showinfo(self._t("Busy"), self._t("Stop parsing before clearing cache."))
            return

        cache_dir = getattr(self, "cache_dir", Path(".cache_http"))
        cache_dir = Path(cache_dir).resolve()

        if not cache_dir.exists():
            messagebox.showinfo(self._t("Cache"), f"{self._t("Cache folder not found:")} {cache_dir}")
            return

        if not messagebox.askyesno("Clear cache", f"Delete cache folder?\n{cache_dir}"):
            return

        try:
            shutil.rmtree(cache_dir)
            self._append_log(f"Cache cleared: {cache_dir}")
        except Exception as e:
            messagebox.showerror(self._t("Error"), f"{self._t("Failed to clear cache:")} {e}")


    def on_pause(self) -> None:
        if getattr(self, "_pause_event", None) is None:
            return
        paused = bool(self._pause_event.is_set())
        if paused:
            self._pause_event.clear()
            self.btn_pause.config(text=self._t("Pause"))
            self._append_log("[progress] resumed")
        else:
            self._pause_event.set()
            self.btn_pause.config(text=self._t("Resume"))
            self.status.set(self._t("Paused"))
            self._append_log("[progress] paused")

    def on_stop(self) -> None:
        if getattr(self, "_cancel_event", None) is None:
            return
        self._cancel_event.set()
        self.status.set(self._t("Stopping..."))
        self._append_log("[progress] stopping...")

    def on_view(self) -> None:
        state_path = Path(self.state_var.get().strip() or "results/jobs_state.json")
        file_to_view = (
            state_path
            if state_path.exists()
            else (self._last_out or _expand_out_template(self.out_var.get().strip() or "results/output_{date}.json"))
        )

        try:
            if self._server is None:
                self._server = start_server(json_path=file_to_view)
            url = "http://127.0.0.1:8765/"
            webbrowser.open(url)
            self._append_log(f"Viewer: {url} (file={file_to_view})")
        except OSError as e:
            messagebox.showerror(self._t("Error"), f"{self._t("Failed to start server:")} {e}")

    def on_open_file(self) -> None:
        p = self._last_out
        if p is None:
            p = _expand_out_template(self.out_var.get().strip() or "results/output_{date}.json")
        p = p.resolve()
        if not p.exists():
            messagebox.showinfo(self._t("File"), f"{self._t("File not found:")} {p}")
            return

        try:
            os.startfile(str(p))  # type: ignore[attr-defined]
        except Exception:
            subprocess.Popen(["cmd", "/c", "start", "", str(p)], shell=False)


def main() -> int:
    _win_set_app_user_model_id("JobSearchUA")
    root = tk.Tk()
    _try_set_app_icon(root)
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
