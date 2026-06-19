"""Доставка HTML-письма.

Три режима (SEND_MODE):
  relay  — через внешний SMTP-аккаунт (SMTP_HOST/USER/PASSWORD).
  direct — прямая доставка на MX-сервер получателя (свой мини-MTA, без аккаунта).
  если ни то ни другое не настроено — письмо сохраняется в out/ как файл.
"""
from __future__ import annotations

import smtplib
import socket
import ssl
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from pathlib import Path

from .config import ROOT, Settings


def _save_to_file(html_body: str) -> Path:
    out_dir = ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"digest_{datetime.now():%Y-%m-%d_%H%M}.html"
    path.write_text(html_body, encoding="utf-8")
    return path


def _build_message(html_body: str, subject: str, settings: Settings) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.mail_from
    msg["To"] = settings.mail_to
    msg["Date"] = formatdate(localtime=True)
    domain = settings.mail_from.split("@")[-1] if "@" in settings.mail_from else "localhost"
    msg["Message-ID"] = make_msgid(domain=domain)
    msg.attach(MIMEText("Для просмотра письма откройте его в HTML-режиме.", "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _recipients(settings: Settings) -> list[str]:
    return [r.strip() for r in settings.mail_to.split(",") if r.strip()]


# --- режим relay -----------------------------------------------------------
def _send_relay(msg: MIMEMultipart, settings: Settings) -> None:
    print(f"Отправка через SMTP {settings.smtp_host}:{settings.smtp_port} ...")
    if settings.smtp_ssl:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ctx) as srv:
            srv.login(settings.smtp_user, settings.smtp_password)
            srv.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as srv:
            srv.starttls(context=ssl.create_default_context())
            srv.login(settings.smtp_user, settings.smtp_password)
            srv.send_message(msg)
    print("[✓] Письмо отправлено (relay).")


# --- режим direct (свой MTA) ----------------------------------------------
def _mx_hosts(domain: str) -> list[str]:
    """MX-серверы домена по приоритету. Фолбэк — сам домен."""
    try:
        import dns.resolver

        records = sorted(dns.resolver.resolve(domain, "MX"), key=lambda r: r.preference)
        return [str(r.exchange).rstrip(".") for r in records]
    except Exception as exc:  # noqa: BLE001
        print(f"  [!] Не удалось получить MX для {domain} ({exc}); пробую сам домен.")
        return [domain]


def _ehlo_name(settings: Settings) -> str:
    if settings.ehlo_hostname:
        return settings.ehlo_hostname
    if "@" in settings.mail_from:
        return settings.mail_from.split("@")[-1]
    return socket.getfqdn() or "localhost"


def _dkim_sign(raw: bytes, settings: Settings) -> bytes:
    """Возвращает заголовок DKIM-Signature (bytes) для письма."""
    import dkim

    key = (ROOT / settings.dkim_private_key).read_bytes()
    headers = [b"From", b"To", b"Subject", b"Date", b"Message-ID", b"MIME-Version", b"Content-Type"]
    sig = dkim.sign(
        message=raw,
        selector=settings.dkim_selector.encode(),
        domain=settings.dkim_domain.encode(),
        privkey=key,
        include_headers=headers,
    )
    return sig


def _send_direct(msg: MIMEMultipart, settings: Settings) -> None:
    sender = settings.mail_from
    ehlo = _ehlo_name(settings)
    raw = msg.as_bytes()
    if settings.dkim_ready:
        raw = _dkim_sign(raw, settings) + raw
        print(f"  DKIM-подпись: selector={settings.dkim_selector}, domain={settings.dkim_domain}")
    else:
        print("  [i] DKIM не настроен — письмо уйдёт без подписи (вероятен спам/отказ).")

    # группируем получателей по домену
    by_domain: dict[str, list[str]] = defaultdict(list)
    for rcpt in _recipients(settings):
        by_domain[rcpt.split("@")[-1]].append(rcpt)

    for domain, rcpts in by_domain.items():
        delivered = False
        last_err: Exception | None = None
        for host in _mx_hosts(domain):
            try:
                print(f"Прямая доставка на {host}:25 (домен {domain}, EHLO {ehlo}) ...")
                with smtplib.SMTP(host, 25, local_hostname=ehlo, timeout=30) as srv:
                    srv.ehlo(ehlo)
                    if srv.has_extn("starttls"):
                        srv.starttls(context=ssl.create_default_context())
                        srv.ehlo(ehlo)
                    srv.mail(sender)
                    code, resp = srv.rcpt(rcpts[0])
                    for extra in rcpts[1:]:
                        srv.rcpt(extra)
                    if code >= 400:
                        raise smtplib.SMTPException(f"RCPT отклонён: {code} {resp!r}")
                    code, resp = srv.data(raw)
                    resp_text = resp.decode(errors="replace") if isinstance(resp, bytes) else str(resp)
                    print(f"  ответ сервера: {code} {resp_text}")
                    if code >= 400:
                        raise smtplib.SMTPDataError(code, resp_text)
                    delivered = True
                    break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                print(f"  [!] {host}: {exc}")
                continue
        if delivered:
            print(f"[✓] Доставлено на {', '.join(rcpts)} (direct).")
        else:
            raise RuntimeError(f"Не удалось доставить на домен {domain}: {last_err}")


def deliver(html_body: str, subject: str, settings: Settings) -> bool:
    """Доставляет письмо. Возвращает True при успехе. При сбое не падает —
    сохраняет HTML в out/ как резерв и возвращает False."""
    mode = settings.send_mode
    try:
        if mode == "direct":
            _send_direct(_build_message(html_body, subject, settings), settings)
            return True
        if mode == "relay" and settings.smtp_ready:
            _send_relay(_build_message(html_body, subject, settings), settings)
            return True
    except Exception as exc:  # noqa: BLE001
        path = _save_to_file(html_body)
        print(f"[!] Доставка не удалась: {exc}")
        print(f"    Письмо сохранено в файл: {path}")
        return False

    path = _save_to_file(html_body)
    print(f"[i] Отправка не настроена (SEND_MODE={mode}, SMTP не заполнен) — письмо сохранено: {path}")
    print(f"    Получатель (когда настроите отправку): {settings.mail_to}")
    return False
