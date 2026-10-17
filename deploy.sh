#!/bin/bash
set -euo pipefail

INSTALL_DIR="/opt/crypto-exkurs-bot"
SERVICE_NAME="crypto-exkurs-bot"

echo "=== Обновление USDT Rate Monitor Bot ==="
echo "  Каталог: $INSTALL_DIR"

cd "$INSTALL_DIR"
git diff --exit-code --quiet
git diff --cached --exit-code --quiet
git fetch origin
"$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/scripts/release.py" --install-dir "$INSTALL_DIR" --service "$SERVICE_NAME" "$@"
