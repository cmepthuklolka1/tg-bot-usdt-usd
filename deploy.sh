#!/bin/bash
set -e

INSTALL_DIR="/opt/usdt-bot"
SERVICE_NAME="usdt-bot"

echo "=== Обновление USDT Rate Monitor Bot ==="
echo "  Каталог: $INSTALL_DIR"

cd "$INSTALL_DIR"
git pull origin master

echo "Обновление зависимостей..."
"$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

echo "✅ Код обновлён. Перезапуск службы..."
sudo systemctl restart "$SERVICE_NAME"

echo "✅ Готово!"
sudo systemctl status "$SERVICE_NAME" --no-pager
