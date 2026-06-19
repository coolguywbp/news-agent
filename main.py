#!/usr/bin/env python3
"""news-agent — мониторинг новостей по тегам с дайджестом на email.

Запуск:  python main.py            (полный цикл)
         python main.py --dry-run  (без отправки: только собрать + сводка + сохранить HTML)
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

from src.config import load_feeds, load_settings, load_tags
from src.fetch import collect
from src.render import render
from src.send import deliver
from src.summarize import summarize


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    settings = load_settings()
    tags = load_tags()
    feeds = load_feeds()

    if not tags:
        print("[!] Список тегов пуст (tags.txt). Нечего искать.")
        return 1
    if not feeds:
        print("[!] Список лент пуст (feeds.txt). Нечего собирать.")
        return 1
    if not dry_run and not settings.mail_to:
        print("[!] Не задан получатель письма (MAIL_TO в .env). Укажите адрес или запустите с --dry-run.")
        return 1

    print(f"Теги ({len(tags)}): {', '.join(tags)}\n")

    articles = collect(feeds, tags, settings.lookback_hours)

    digest = summarize(articles, settings)

    end = datetime.now()
    start = end - timedelta(hours=settings.lookback_hours)
    period_label = f"{start:%d.%m %H:%M} – {end:%d.%m %H:%M}"
    html_body = render(digest, tags, period_label)

    subject = f"Дайджест новостей за {end:%d.%m.%Y} — {len(digest.get('items', []))} событий"

    if dry_run:
        from src.send import _save_to_file
        path = _save_to_file(html_body)
        print(f"[dry-run] HTML сохранён: {path}")
    else:
        deliver(html_body, subject, settings)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
