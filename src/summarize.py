"""Сводка новостей по важности через DeepSeek API.

Чтобы исключить выдуманные ссылки, в модель передаются пронумерованные
статьи, а в ответе она ссылается только на их номера (article_ids).
Реальные URL берутся из исходных данных при вёрстке.
"""
from __future__ import annotations

import json

import requests

from .config import Settings
from .fetch import Article

SYSTEM_PROMPT = (
    "Ты — ассистент-аналитик пресс-службы. Тебе дают список новостей за прошедшие сутки, "
    "упомянувших отслеживаемые компании. Сгруппируй и отранжируй их по важности для руководства. "
    "Объединяй сообщения об одном событии в один пункт. Пиши деловым русским языком, кратко и по делу."
)

INSTRUCTIONS = """\
Проанализируй новости ниже и верни СТРОГО валидный JSON без markdown-обрамления вида:
{
  "summary": "1-3 предложения — общий обзор дня по отслеживаемым компаниям",
  "items": [
    {
      "importance": "high" | "medium" | "low",
      "title": "краткий заголовок события",
      "text": "2-4 предложения сути со ключевыми фактами и цифрами",
      "companies": ["название компании", ...],
      "article_ids": [1, 5]   // номера ВСЕХ относящихся к событию статей из списка
    }
  ]
}
Правила:
- Используй ТОЛЬКО номера статей из предоставленного списка, не выдумывай источники.
- Сортируй items от самого важного к наименее важному.
- importance=high — крупные сделки, контракты, отзывы, аварии, кадровые/финансовые/регуляторные решения; low — рутина и упоминания вскользь.
- Если по компании нет значимых новостей — не добавляй пустых пунктов.

Новости:
"""


def _articles_block(articles: list[Article]) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        lines.append(
            f"[{i}] ({a.source}, {a.date_str or 'дата н/д'}; теги: {', '.join(a.tags)}) "
            f"{a.title}. {a.summary[:400]}"
        )
    return "\n".join(lines)


def summarize(articles: list[Article], settings: Settings) -> dict:
    """Возвращает dict со сводкой. items[*]['articles'] — реальные Article."""
    if not articles:
        return {"summary": "За прошедшие сутки значимых новостей по отслеживаемым тегам не найдено.", "items": []}

    if not settings.deepseek_api_key:
        raise RuntimeError("Не задан DEEPSEEK_API_KEY в .env")

    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": INSTRUCTIONS + _articles_block(articles)},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "stream": False,
    }

    print("Запрос к DeepSeek для составления сводки...")
    resp = requests.post(
        f"{settings.deepseek_base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    data = json.loads(content)

    # Подставляем реальные статьи по article_ids
    for item in data.get("items", []):
        ids = item.get("article_ids", []) or []
        item["articles"] = [articles[i - 1] for i in ids if isinstance(i, int) and 1 <= i <= len(articles)]
    return data
