#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="usdt-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
CURRENT_USER="$(whoami)"

echo "=== USDT Rate Monitor Bot — установка ==="
echo

# 1. Виртуальное окружение
echo "[1/4] Создание виртуального окружения..."
python3 -m venv "$SCRIPT_DIR/venv"

# 2. Зависимости
echo "[2/4] Установка зависимостей..."
"$SCRIPT_DIR/venv/bin/pip" install -q --upgrade pip
"$SCRIPT_DIR/venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"

# 3. Конфигурация
echo "[3/4] Настройка конфигурационных файлов..."
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    echo "  → Создан .env (заполните BOT_TOKEN и ADMIN_ID перед запуском)"
else
    echo "  → .env уже существует, пропускаем"
fi

for f in whitelist banned_sellers pinned_messages; do
    if [ ! -f "$SCRIPT_DIR/config/${f}.json" ]; then
        cp "$SCRIPT_DIR/config/${f}.example.json" "$SCRIPT_DIR/config/${f}.json"
        echo "  → Создан config/${f}.json"
    fi
done

# 4. Файл systemd-службы
echo "[4/4] Создание файла службы systemd..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=USDT Rate Monitor Bot
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${SCRIPT_DIR}/venv/bin/python ${SCRIPT_DIR}/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload

echo
echo "✅ Установка завершена!"
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Перед запуском отредактируйте .env:"
echo "  nano $SCRIPT_DIR/.env"
echo
echo "  Добавить в автозапуск и запустить службу:"
echo "  sudo systemctl enable $SERVICE_NAME"
echo "  sudo systemctl start $SERVICE_NAME"
echo
echo "  Проверить статус:"
echo "  sudo systemctl status $SERVICE_NAME"
echo
echo "  Просмотр логов в реальном времени:"
echo "  sudo journalctl -u $SERVICE_NAME -f"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
