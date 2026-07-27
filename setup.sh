#!/bin/bash
set -e
echo "AutoFlow Unified — установка"
apt update && apt upgrade -y
apt install -y curl git ufw nginx certbot python3-certbot-nginx
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin
ufw --force reset
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
mkdir -p /opt/autoflow/data/sessions /opt/autoflow/data/logs /opt/autoflow/data/auth_temp /opt/autoflow/backups /opt/autoflow/templates
cd /opt/autoflow
KEY=$(openssl rand -hex 32)
cat > .env <<EOF
SECRET_KEY=$KEY
DEV_MODE=False
TELEGRAM_API_ID=0
TELEGRAM_API_HASH=CHANGE_ME
TELEGRAM_BOT_TOKEN=CHANGE_ME
MAILER_DELAY_MIN=30
MAILER_DELAY_MAX=90
MAX_TG_ACCOUNTS=5
ADMIN_TELEGRAM_USERNAME=Cxentrall
ADMIN_TELEGRAM_ID=
EOF
echo "Готово. Скопируй файлы в /opt/autoflow, заполни .env, затем: docker compose up -d --build"
echo "SECRET_KEY: $KEY"
