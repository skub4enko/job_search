# Job search UA parser

CLI-парсер вакансий по Украине (remote-only по умолчанию) с выгрузкой в JSON и инкрементальным обновлением (merge).

Источники:\n- Work.ua (scrape)\n- Robota.ua (API)\n- DOU Jobs (RSS + scrape деталей)\n- Jobs.ua (scrape)\n- OLX.ua (Работа) (scrape)\n- GRC (jobs.grc.ua) (scrape, best-effort)\n- Talent.UA (best-effort)\n- Jooble (REST API, нужен ключ)

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Query (что искать)

`--query` — это название профессии/роль/ключевые слова.

Можно несколько запросов:

```powershell
python -m job_search --query "Python developer, QA engineer" --out "jobs_{date}.json"
```

или так:

```powershell
python -m job_search --query "Python developer" --query "QA engineer" --out "jobs_{date}.json"
```

## Имя файла с датой

`--out` поддерживает шаблоны:
- `{date}` → `YYYY-MM-DD`
- `{datetime}` → `YYYY-MM-DD_HH-MM`

Пример:

```powershell
python -m job_search --query "Python" --out "output_{date}.json"
```

## Обновление данных (merge)

Если вы используете `--out` с датой, для корректного merge нужен файл состояния `--state`.
По умолчанию он будет `jobs_state.json`.

```powershell
python -m job_search --query "Python" --out "jobs_{date}.json" --state jobs_state.json
```

- `jobs_state.json` хранит общую базу (с `first_seen_at/last_seen_at/is_active`).
- `jobs_YYYY-MM-DD.json` — снимок на дату запуска.

## Jooble

Jooble работает через REST API и требует ключ.

Вариант 1 — переменная окружения:

```powershell
$env:JOOBLE_API_KEY = "..."
python -m job_search --query "Python" --sources jooble --out "jooble_{date}.json"
```

Вариант 2 — параметр CLI:

```powershell
python -m job_search --query "Python" --sources jooble --jooble-api-key "..." --out "jooble_{date}.json"
```

## Поля в JSON

Каждая запись:
- `source`: `workua` | `rabotaua` | `dou` | `jooble`
- `url`
- `title`
- `company`
- `location`
- `salary`
- `published_at` (если получилось извлечь)
- `remote` (bool)
- `emails` (массив)
- `phones` (массив)
- `description` (текст/сниппет)
- `scraped_at` (ISO 8601)
- `first_seen_at` / `last_seen_at` (ISO 8601)
- `is_active` (true если вакансия попалась в последнем прогоне)

## Примечания

- Контакты (email/телефон) извлекаются регулярками из текста вакансии; на некоторых площадках их может не быть.
- Верстка сайтов меняется. Если какой-то источник начал отдавать пустые поля — пришлите 1–2 HTML-страницы (поиск и вакансия), адаптер можно быстро поправить.

## GUI

Запуск окна (Tkinter):

```powershell
python -m job_search.gui
```

В окне:
- поле "Вакансии" — список через запятую
- "Искать / обновить JSON" — обновляет `jobs_state.json` и пишет снимок в `output_{date}.json`
- "Просмотреть в браузере" — поднимает локальный сервер и открывает страницу

## Локальный сервер (viewer)

Запуск сервера вручную:

```powershell
python -m job_search.server --file jobs_state.json --port 8765
```

Открыть в браузере: http://127.0.0.1:8765/

## Indeed

Прямой парсинг Indeed часто блокируется, поэтому источник `indeed` сделан через сторонний API (ScrapeOps Structured Data).

Ключ можно задать так:

```powershell
$env:SCRAPEOPS_API_KEY = "..."
python -m job_search --sources indeed --query "Python developer" --out "indeed_{date}.json" --state jobs_state.json
```

или через параметр:

```powershell
python -m job_search --sources indeed --query "Python developer" --scrapeops-api-key "..." --out "indeed_{date}.json" --state jobs_state.json
```


## api.txt (ключи для GUI)

- При запуске из исходников GUI читает `assets/api.txt` (если файл есть).
- В собранном EXE ключи не вшиваются: положи `api.txt` рядом с `JobSearchUA.exe` (в той же папке).

Поддерживаются форматы:
- `https://jooble.org - <API_KEY>`
- или письмо/текст, где встречается UUID‑ключ Jooble
- `SCRAPEOPS_API_KEY=<key>` (если когда-нибудь понадобится indeed)

## Сборка EXE (Windows)

Собирается в `dist/JobSearchUA.exe` и включает `assets/icon.(ico|png)` и `assets/beep.mp3`, но НЕ включает `assets/api.txt`.

Важно: сборка GUI требует рабочий Tkinter (Tcl/Tk) в твоём Python. Проверка:

```powershell
python -c "import tkinter as tk; r=tk.Tk(); r.destroy()"
```

Если проверка падает с ошибкой init.tcl, переустанови Python с опцией "tcl/tk and IDLE".

### Парсер без GUI

Если Tkinter не работает, можно собрать консольный EXE парсер (с бипом по умолчанию):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_parser_exe.ps1
```

Результат: `dist/JobSearchUA_Parser.exe`

PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_exe.ps1
```

или запуск из cmd:

```bat
tools\build_exe.bat
```

