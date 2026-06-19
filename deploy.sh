#!/usr/bin/env bash
#
# news-agent — автоматическое развёртывание на Ubuntu/Debian.
# Запуск:  ./deploy.sh
# Можно передать ключ DeepSeek без интерактива:
#          DEEPSEEK_API_KEY=sk-xxxx ./deploy.sh
#
set -euo pipefail
cd "$(dirname "$0")"

echo "==================================================="
echo "  news-agent — развёртывание"
echo "==================================================="

# 1) Системные зависимости -------------------------------------------------
echo "==> [1/5] Системные пакеты (python3, venv, openssl)..."
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3 python3-venv python3-pip openssl ca-certificates
else
  echo "    apt-get не найден — установите python3, python3-venv и openssl вручную."
fi

# 2) Виртуальное окружение + зависимости -----------------------------------
echo "==> [2/5] Виртуальное окружение и Python-пакеты..."
python3 -m venv venv
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -r requirements.txt

# 3) Конфигурация .env ------------------------------------------------------
echo "==> [3/5] Конфигурация (.env)..."
if [ ! -f .env ]; then
  cp .env.example .env
  if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
    KEY="$DEEPSEEK_API_KEY"
  else
    read -rp "    Введите DeepSeek API key (sk-...): " KEY
  fi
  sed -i "s|^DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=${KEY}|" .env

  if [ -n "${MAIL_TO:-}" ]; then
    TO="$MAIL_TO"
  else
    read -rp "    Введите email получателя дайджеста: " TO
  fi
  sed -i "s|^MAIL_TO=.*|MAIL_TO=${TO}|" .env

  # Домен отправителя: по умолчанию = домен получателя (можно переопределить SENDER_DOMAIN=...)
  DOMAIN="${SENDER_DOMAIN:-${TO##*@}}"
  sed -i "s|^SMTP_FROM=.*|SMTP_FROM=news-agent@${DOMAIN}|" .env
  sed -i "s|^DKIM_DOMAIN=.*|DKIM_DOMAIN=${DOMAIN}|" .env
  echo "    .env создан (домен отправителя: ${DOMAIN})."
else
  echo "    .env уже есть — не трогаю."
fi

# 4) DKIM-ключ --------------------------------------------------------------
echo "==> [4/5] DKIM-ключ..."
NEW_KEY=0
if [ ! -f keys/dkim_private.pem ]; then
  mkdir -p keys && chmod 700 keys
  openssl genrsa -out keys/dkim_private.pem 2048 2>/dev/null
  openssl rsa -in keys/dkim_private.pem -pubout -out keys/dkim_public.pem 2>/dev/null
  chmod 600 keys/dkim_private.pem
  NEW_KEY=1
  echo "    Сгенерирован новый ключ."
else
  echo "    Ключ уже есть — переиспользую (DNS-запись менять не нужно)."
fi

# 5) Итог + DNS-запись ------------------------------------------------------
echo "==> [5/5] Готово."
SEL=$(grep '^DKIM_SELECTOR=' .env | cut -d= -f2)
DOM=$(grep '^DKIM_DOMAIN=' .env | cut -d= -f2)
PUB=$(grep -v -- '-----' keys/dkim_public.pem | tr -d '\n')
IP=$(./venv/bin/python -c "import urllib.request;print(urllib.request.urlopen('https://api.ipify.org',timeout=8).read().decode())" 2>/dev/null || echo "не определён")

echo ""
echo "---------------------------------------------------"
if [ "$NEW_KEY" = "1" ]; then
  echo "ВАЖНО: сгенерирован новый DKIM-ключ. Опубликуйте TXT-запись в DNS ${DOM}:"
  echo ""
  echo "  Имя:      ${SEL}._domainkey"
  echo "  Тип:      TXT"
  echo "  Значение: v=DKIM1; k=rsa; p=${PUB}"
  echo ""
  echo "Без неё письма уйдут без валидной подписи (вероятен спам)."
else
  echo "DKIM-ключ переиспользован — существующая DNS-запись остаётся в силе."
fi
echo ""
echo "Внешний IP этой машины: ${IP}"
echo "(при желании добавьте его в SPF домена ${DOM} для прохождения SPF)"
echo "---------------------------------------------------"
echo ""
echo "Запуск мониторинга:        ./venv/bin/python main.py"
echo "Тест без отправки письма:   ./venv/bin/python main.py --dry-run"
echo "==================================================="
