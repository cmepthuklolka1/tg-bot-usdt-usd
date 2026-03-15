#!/bin/bash
set -e

SERVICE_NAME="usdt-bot"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Обновление USDT Rate Monitor Bot ==="

cd "$SCRIPT_DIR"
git pull origin master

echo "✅ Код обновлён. Перезапуск службы..."
sudo systemctl restart "$SERVICE_NAME"

echo "✅ Готово!"
sudo systemctl status "$SERVICE_NAME" --no-pager
