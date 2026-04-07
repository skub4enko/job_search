from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import httpx

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

from job_search.runner import run
from job_search.store import load_payload, merge_payload
from job_search.notify import asset_path, play_sound_async


def _ensure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


_ensure_utf8()


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


def _parse_queries(values: list[str]) -> list[str]:
    queries: list[str] = []
    for v in values:
        parts = [p.strip() for p in v.replace(";", ",").split(",")]
        for p in parts:
            if p:
                queries.append(p)

    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        k = q.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(q)
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="job_search",
        description="Парсер украинских площадок вакансий (remote-only) с сохранением/обновлением JSON.",
    )

    p.add_argument(
        "--query",
        required=True,
        action="append",
        help=(
            "Запрос (название профессии/ключевые слова). Можно несколько: "
            "`--query \"Python developer, QA engineer\"` или несколько флагов --query."
        ),
    )

    p.add_argument("--city", default="", help="Город/локация (опционально, для remote можно оставить пустым).")

    p.add_argument(
        "--sources",
        default="workua,rabotaua,dou,jooble",
        help="Источники через запятую (например: workua,rabotaua,dou,jooble,indeed).",
    )

    p.add_argument("--max-pages", type=int, default=2, help="Сколько страниц выдачи парсить на каждом источнике.")
    p.add_argument("--limit", type=int, default=100, help="Максимум вакансий на источник.")

    p.add_argument(
        "--out",
        default="results/jobs_{date}.json",
        help=(
            "Куда писать результат. Поддерживает шаблоны: {date} (YYYY-MM-DD), {datetime} (YYYY-MM-DD_HH-MM). "
            "Пример: jobs_{date}.json"
        ),
    )

    p.add_argument(
        "--state",
        type=Path,
        default=None,
        help=(
            "Файл состояния для merge/обновления. Если не указан и --out без шаблонов, "
            "используется тот же файл что и --out. Если --out с {date}/{datetime}, по умолчанию jobs_state.json."
        ),
    )

    p.add_argument("--cache-dir", type=Path, default=Path(".cache_http"), help="Директория кэша HTML.")
    p.add_argument("--no-cache", action="store_true", help="Отключить чтение/запись кэша.")
    p.add_argument("--timeout", type=float, default=20.0, help="Таймаут HTTP запросов (сек).")
    p.add_argument("--concurrency", type=int, default=10, help="Параллельность загрузки страниц вакансий.")
    p.add_argument("--verbose", action="store_true", help="Больше логов в stderr.")

    p.add_argument("--beep", action="store_true", help="Play notification sound (assets/beep.mp3) on completion.")

    p.add_argument(
        "--include-non-remote",
        action="store_true",
        help="Не ограничивать выдачу remote-only (по умолчанию ищем только удалёнку).",
    )

    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Перезаписать JSON только свежими результатами (без merge/обновления).",
    )

    p.add_argument(
        "--jooble-api-key",
        default="",
        help="Jooble REST API key (если не задан, берётся из переменной окружения JOOBLE_API_KEY).",
    )

    p.add_argument(
        "--scrapeops-api-key",
        default="",
        help="ScrapeOps API key (для источника indeed). Если не задан, берётся из переменной окружения SCRAPEOPS_API_KEY.",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.jooble_api_key:
        os.environ["JOOBLE_API_KEY"] = args.jooble_api_key
    if args.scrapeops_api_key:
        os.environ["SCRAPEOPS_API_KEY"] = args.scrapeops_api_key

    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    if not sources:
        print("Нужно указать хотя бы один источник в --sources.", file=sys.stderr)
        return 2

    queries = _parse_queries(args.query)
    if not queries:
        print("Нужно указать хотя бы один непустой запрос в --query.", file=sys.stderr)
        return 2

    out_path = _expand_out_template(str(args.out))
    uses_template = ("{date}" in str(args.out)) or ("{datetime}" in str(args.out))

    if args.state is None:
        state_path = Path("results/jobs_state.json") if uses_template else out_path
    else:
        state_path = args.state

    remote_only = not args.include_non_remote

    try:
        fresh_jobs = []
        for q in queries:
            fresh_jobs.extend(
                run(
                    query=q,
                    city=args.city,
                    remote_only=remote_only,
                    sources=sources,
                    max_pages=args.max_pages,
                    limit=args.limit,
                    cache_dir=args.cache_dir,
                    use_cache=not args.no_cache,
                    timeout_s=args.timeout,
                    concurrency=args.concurrency,
                    verbose=args.verbose,
                )
            )
    except httpx.HTTPError as e:
        print(f"HTTP ошибка: {e}", file=sys.stderr)
        print("Проверьте доступ в интернет/прокси/VPN и повторите.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1

    fresh_payload = [asdict(j) for j in fresh_jobs]

    if args.overwrite:
        payload = fresh_payload
    else:
        existing = load_payload(state_path)
        payload = merge_payload(existing, fresh_payload)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    active = sum(1 for r in payload if isinstance(r, dict) and r.get("is_active"))
    print(f"OK: {len(payload)} записей (active={active}) -> {out_path}")
    if args.beep:
        play_sound_async(asset_path("beep.mp3"))
    if not args.overwrite:
        print(f"STATE: {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
