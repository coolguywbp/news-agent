"""Сбор новостей из RSS-лент и фильтрация по тегам за заданный период."""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from .config import Feed

UA = "Mozilla/5.0 (compatible; news-agent/1.0)"


@dataclass
class Article:
    title: str
    link: str
    summary: str
    source: str
    published: datetime | None
    tags: list[str] = field(default_factory=list)

    @property
    def date_str(self) -> str:
        if not self.published:
            return ""
        return self.published.astimezone().strftime("%d.%m.%Y %H:%M")


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            return datetime.fromtimestamp(time.mktime(val), tz=timezone.utc)
    return None


def _compile_tag_patterns(tags: list[str]) -> list[tuple[str, re.Pattern]]:
    """Для каждого тега — регэксп с границами слова (без учёта регистра, unicode)."""
    patterns = []
    for tag in tags:
        # \b плохо работает на стыке кириллицы/латиницы, поэтому используем
        # «не буквенно-цифровой или край строки» вокруг тега.
        esc = re.escape(tag)
        pat = re.compile(rf"(?<![\w]){esc}(?![\w])", re.IGNORECASE | re.UNICODE)
        patterns.append((tag, pat))
    return patterns


def fetch_feed(feed: Feed, timeout: int = 20) -> list[Article]:
    """Скачивает и парсит одну ленту. Ошибки сети не валят весь прогон."""
    try:
        resp = requests.get(feed.url, headers={"User-Agent": UA}, timeout=timeout)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:  # noqa: BLE001
        print(f"  [!] {feed.name}: ошибка загрузки — {exc}")
        return []

    articles: list[Article] = []
    for entry in parsed.entries:
        title = _strip_html(entry.get("title", ""))
        link = entry.get("link", "").strip()
        summary = _strip_html(entry.get("summary", "") or entry.get("description", ""))
        if not title or not link:
            continue
        articles.append(
            Article(
                title=title,
                link=link,
                summary=summary,
                source=feed.name,
                published=_parse_date(entry),
            )
        )
    return articles


def collect(feeds: list[Feed], tags: list[str], lookback_hours: int) -> list[Article]:
    """Собирает все ленты, фильтрует по тегам и по дате (последние N часов)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    patterns = _compile_tag_patterns(tags)

    seen_links: set[str] = set()
    matched: list[Article] = []

    print(f"Сбор новостей из {len(feeds)} лент (период: {lookback_hours} ч)...")
    for feed in feeds:
        items = fetch_feed(feed)
        kept = 0
        for art in items:
            # фильтр по дате: если дата неизвестна — оставляем (лучше лишнее, чем пропуск)
            if art.published and art.published < cutoff:
                continue
            haystack = f"{art.title} {art.summary}"
            hit_tags = [tag for tag, pat in patterns if pat.search(haystack)]
            if not hit_tags:
                continue
            if art.link in seen_links:
                continue
            seen_links.add(art.link)
            art.tags = sorted(set(hit_tags))
            matched.append(art)
            kept += 1
        print(f"  {feed.name}: {len(items)} новостей, по тегам подошло {kept}")

    # свежие — выше
    matched.sort(key=lambda a: a.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    print(f"Итого по тегам за период: {len(matched)} материалов.")
    return matched
