#!/bin/bash
set -e

INSTALL_DIR="/opt/usdt-bot"
SERVICE_NAME="usdt-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
CURRENT_USER="$(whoami)"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== USDT Rate Monitor Bot — установка ==="
echo "  Целевой каталог: $INSTALL_DIR"
echo

# 1. Копирование файлов в /opt/usdt-bot
echo "[1/5] Подготовка каталога приложения..."
if [ "$SOURCE_DIR" != "$INSTALL_DIR" ]; then
    sudo mkdir -p "$INSTALL_DIR"
    sudo rsync -a --exclude='venv/' --exclude='__pycache__/' \
        "$SOURCE_DIR/" "$INSTALL_DIR/"
    sudo chown -R "$CURRENT_USER:$CURRENT_USER" "$INSTALL_DIR"
    echo "  → Файлы скопированы в $INSTALL_DIR"
else
    echo "  → Уже в $INSTALL_DIR, пропускаем копирование"
fi

# 2. Виртуальное окружение
echo "[2/5] Создание виртуального окружения..."
python3 -m venv "$INSTALL_DIR/venv"

# 3. Зависимости
echo "[3/5] Установка зависимостей..."
"$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

# 4. Конфигурация
echo "[4/5] Настройка конфигурационных файлов..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo "  → Создан .env (заполните BOT_TOKEN и ADMIN_ID перед запуском)"
else
    echo "  → .env уже существует, пропускаем"
fi

for f in whitelist banned_sellers pinned_messages user_settings; do
    if [ ! -f "$INSTALL_DIR/config/${f}.json" ]; then
        cp "$INSTALL_DIR/config/${f}.example.json" "$INSTALL_DIR/config/${f}.json"
        echo "  → Создан config/${f}.json"
    fi
done

# 5. Файл systemd-службы
echo "[5/5] Создание файла службы systemd..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=USDT Rate Monitor Bot
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/main.py
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
echo "   Приложение установлено в: $INSTALL_DIR"
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Перед запуском отредактируйте .env:"
echo "  nano $INSTALL_DIR/.env"
echo
echo "  Добавить в автозапуск и запустить службу:"
echo "  sudo systemctl enable $SERVICE_NAME"
echo "  sudo systemctl start $SERVICE_NAME"
echo
echo "  Проверить статус:"
echo "  sudo systemctl status $SERVICE_NAME"
echo
echo "  Перезапустить службу:"
echo "  sudo systemctl restart $SERVICE_NAME"
echo
echo "  Обновить код и перезапустить (deploy):"
echo "  bash $INSTALL_DIR/deploy.sh"
echo
echo "  Просмотр логов в реальном времени:"
echo "  sudo journalctl -u $SERVICE_NAME -f"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
