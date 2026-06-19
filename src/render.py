"""Вёрстка сводки в HTML-письмо (inline-стили для совместимости с почтой)."""
from __future__ import annotations

import html
from datetime import datetime

from .fetch import Article

IMP = {
    "high": ("#c0392b", "Высокая"),
    "medium": ("#d68910", "Средняя"),
    "low": ("#7f8c8d", "Низкая"),
}


def _esc(s: str) -> str:
    return html.escape(s or "")


def _sources_html(articles: list[Article]) -> str:
    if not articles:
        return ""
    links = []
    for a in articles:
        meta = " · ".join(x for x in [_esc(a.source), _esc(a.date_str)] if x)
        links.append(
            f'<li style="margin:2px 0;">'
            f'<a href="{_esc(a.link)}" style="color:#2563eb;text-decoration:none;">{_esc(a.title)}</a>'
            f'<span style="color:#94a3b8;font-size:12px;"> — {meta}</span></li>'
        )
    return (
        '<div style="margin-top:8px;">'
        '<div style="font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">Источники</div>'
        f'<ul style="margin:0;padding-left:18px;">{"".join(links)}</ul></div>'
    )


def _item_html(item: dict) -> str:
    color, label = IMP.get(item.get("importance", "medium"), IMP["medium"])
    companies = item.get("companies") or []
    chips = "".join(
        f'<span style="display:inline-block;background:#eef2ff;color:#3730a3;border-radius:10px;'
        f'padding:2px 8px;font-size:11px;margin:0 4px 4px 0;">{_esc(c)}</span>'
        for c in companies
    )
    return f"""
    <tr><td style="padding:16px 0;border-bottom:1px solid #eef0f3;">
      <div style="margin-bottom:6px;">
        <span style="display:inline-block;background:{color};color:#fff;border-radius:4px;
              padding:2px 8px;font-size:11px;font-weight:600;text-transform:uppercase;">{label}</span>
      </div>
      <div style="font-size:17px;font-weight:700;color:#0f172a;line-height:1.3;margin-bottom:6px;">{_esc(item.get('title',''))}</div>
      <div style="font-size:14px;color:#334155;line-height:1.55;">{_esc(item.get('text',''))}</div>
      <div style="margin-top:8px;">{chips}</div>
      {_sources_html(item.get('articles', []))}
    </td></tr>"""


def render(digest: dict, tags: list[str], period_label: str) -> str:
    items = digest.get("items", [])
    overview = digest.get("summary", "")
    date_str = datetime.now().strftime("%d.%m.%Y")

    items_html = "".join(_item_html(it) for it in items) if items else (
        '<tr><td style="padding:24px 0;color:#64748b;font-size:14px;">'
        'За указанный период значимых новостей по отслеживаемым тегам не найдено.</td></tr>'
    )

    tags_line = ", ".join(_esc(t) for t in tags)

    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);">
  <tr><td style="background:#0f172a;padding:24px 28px;">
    <div style="color:#fff;font-size:20px;font-weight:700;">Мониторинг новостей</div>
    <div style="color:#94a3b8;font-size:13px;margin-top:4px;">Дайджест за {date_str} · период {period_label}</div>
  </td></tr>
  <tr><td style="padding:20px 28px;background:#f8fafc;border-bottom:1px solid #eef0f3;">
    <div style="font-size:14px;color:#334155;line-height:1.55;">{_esc(overview)}</div>
  </td></tr>
  <tr><td style="padding:0 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{items_html}</table>
  </td></tr>
  <tr><td style="padding:16px 28px 24px;color:#94a3b8;font-size:12px;line-height:1.5;">
    Отслеживаемые теги: {tags_line}.<br>
    Сформировано автоматически news-agent. Сводка подготовлена с помощью DeepSeek.
  </td></tr>
</table>
</td></tr></table></body></html>"""
