"""Загрузка конфигурации, тегов и списка RSS-лент."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


def _read_lines(path: Path) -> list[str]:
    """Читает непустые строки файла, отбрасывая комментарии (#) и пробелы."""
    if not path.exists():
        return []
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def load_tags() -> list[str]:
    """Список тегов из tags.txt (или tags.txt.example, если своего файла ещё нет)."""
    path = ROOT / "tags.txt"
    if not path.exists():
        path = ROOT / "tags.txt.example"
    return _read_lines(path)


@dataclass
class Feed:
    url: str
    name: str


def load_feeds() -> list[Feed]:
    """Список RSS-лент из feeds.txt. Формат строки: URL | Название."""
    feeds: list[Feed] = []
    for line in _read_lines(ROOT / "feeds.txt"):
        if "|" in line:
            url, name = line.split("|", 1)
            feeds.append(Feed(url.strip(), name.strip()))
        else:
            url = line.strip()
            # имя по домену, если не задано
            host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
            feeds.append(Feed(url, host))
    return feeds


@dataclass
class Settings:
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", "").strip())
    deepseek_model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip())
    deepseek_base_url: str = field(default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip())
    lookback_hours: int = field(default_factory=lambda: int(os.getenv("LOOKBACK_HOURS", "24")))
    mail_to: str = field(default_factory=lambda: os.getenv("MAIL_TO", "").strip())
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "").strip())
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "465") or "465"))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", "").strip())
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", "").strip())
    smtp_from: str = field(default_factory=lambda: os.getenv("SMTP_FROM", "").strip())
    smtp_ssl: bool = field(default_factory=lambda: os.getenv("SMTP_SSL", "true").strip().lower() in ("1", "true", "yes"))
    # Режим отправки: relay (через внешний SMTP-аккаунт) или direct (прямо на MX получателя)
    send_mode: str = field(default_factory=lambda: os.getenv("SEND_MODE", "relay").strip().lower())
    # Адрес отправителя и имя для EHLO при прямой отправке
    ehlo_hostname: str = field(default_factory=lambda: os.getenv("EHLO_HOSTNAME", "").strip())
    # DKIM-подпись (для direct): селектор, домен и путь к приватному ключу
    dkim_selector: str = field(default_factory=lambda: os.getenv("DKIM_SELECTOR", "").strip())
    dkim_domain: str = field(default_factory=lambda: os.getenv("DKIM_DOMAIN", "").strip())
    dkim_private_key: str = field(default_factory=lambda: os.getenv("DKIM_PRIVATE_KEY", "keys/dkim_private.pem").strip())

    @property
    def smtp_ready(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @property
    def mail_from(self) -> str:
        return self.smtp_from or self.smtp_user or "news-agent@localhost"

    @property
    def dkim_ready(self) -> bool:
        return bool(self.dkim_selector and self.dkim_domain and (ROOT / self.dkim_private_key).exists())


def load_settings() -> Settings:
    return Settings()
