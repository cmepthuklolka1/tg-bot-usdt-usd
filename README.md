# 💱 USDT/USD Rate Monitor Bot

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-blue)](https://docs.aiogram.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

Приватный Telegram-бот для мониторинга актуальных курсов USDT/RUB. Агрегирует данные из трёх источников и автоматически обновляет закреплённое сообщение каждый час.

---

## 📊 Источники данных

| Источник | Что парсим |
|---|---|
| **ЦБ РФ** | Официальный курс USD/RUB |
| **BestChange.ru** | Топ-1 и топ-10 обменников Сбер → USDT BEP20 |
| **Bybit P2P** | Топ-10 продавцов USDT за RUB (лимит ≥ 100 000 ₽) |

---

## ✨ Функции

- 📌 Одно закреплённое сообщение с курсами, обновляемое на месте (не спамит чат)
- 🔄 Автообновление каждый час в фоне
- ⚡ Ручное обновление по кнопке
- 🔒 Приватный доступ — только вайтлист пользователей
- 🚫 Фильтрация продавцов Bybit по чёрному списку
- 👑 Панель администратора для управления доступом и чёрным списком

---

## 🚀 Установка

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/cmepthuklolka1/tg-bot-usdt-usd.git
cd tg-bot-usdt-usd
```

### 2. Создайте виртуальное окружение и установите зависимости

```bash
python -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Настройте переменные окружения

```bash
cp .env.example .env
```

Отредактируйте `.env`:

```env
BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_ID=ваш_telegram_id
```

### 4. Создайте конфигурационные файлы

```bash
# Linux / macOS
cp config/whitelist.example.json config/whitelist.json
cp config/banned_sellers.example.json config/banned_sellers.json
cp config/pinned_messages.example.json config/pinned_messages.json

# Windows
copy config\whitelist.example.json config\whitelist.json
copy config\banned_sellers.example.json config\banned_sellers.json
copy config\pinned_messages.example.json config\pinned_messages.json
```

---

## ▶️ Запуск

```bash
python main.py
```

---

## 🔧 Управление как службой

### Linux — systemd

Создайте файл службы `/etc/systemd/system/usdt-bot.service`:

```ini
[Unit]
Description=USDT Rate Monitor Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/tg-bot-usdt-usd
ExecStart=/path/to/tg-bot-usdt-usd/venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Управление службой:

```bash
# Активировать и запустить
sudo systemctl daemon-reload
sudo systemctl enable usdt-bot
sudo systemctl start usdt-bot

# Статус
sudo systemctl status usdt-bot

# Остановить / перезапустить
sudo systemctl stop usdt-bot
sudo systemctl restart usdt-bot

# Логи
sudo journalctl -u usdt-bot -f
```

### Windows — NSSM

Установите [NSSM](https://nssm.cc/), затем в командной строке с правами администратора:

```bat
nssm install USDTBot "C:\path\to\venv\Scripts\python.exe" "C:\path\to\tg-bot-usdt-usd\main.py"
nssm set USDTBot AppDirectory "C:\path\to\tg-bot-usdt-usd"
nssm start USDTBot
```

Управление:

```bat
nssm start USDTBot
nssm stop USDTBot
nssm restart USDTBot
nssm status USDTBot
nssm remove USDTBot confirm
```

---

## 🔄 Обновление проекта

```bash
# Остановить службу (если запущена)
sudo systemctl stop usdt-bot        # Linux
# или
nssm stop USDTBot                   # Windows

# Получить обновления
git pull origin main

# Обновить зависимости (если изменился requirements.txt)
pip install -r requirements.txt

# Запустить службу снова
sudo systemctl start usdt-bot       # Linux
# или
nssm start USDTBot                  # Windows
```

---

## 📁 Структура проекта

```
tg-bot-usdt-usd/
├── main.py                     # Точка входа + фоновое автообновление
├── requirements.txt
├── .env.example                # Шаблон переменных окружения
├── config/
│   ├── whitelist.example.json  # Шаблон вайтлиста
│   ├── banned_sellers.example.json
│   └── pinned_messages.example.json
└── src/
    ├── config.py               # Настройки приложения
    ├── domain/
    │   └── models.py           # Pydantic-модели данных
    ├── handlers/
    │   ├── user.py             # Команды пользователя, генерация отчёта
    │   └── admin.py            # Команды администратора (FSM)
    ├── keyboards/
    │   └── menus.py            # Inline-клавиатуры
    ├── services/
    │   ├── cbrf.py             # Парсинг ЦБ РФ (XML)
    │   ├── bestchange.py       # Парсинг BestChange (HTML)
    │   └── bybit_p2p.py        # Bybit P2P API (JSON)
    └── utils/
        ├── storage.py          # JSON-хранилище (вайтлист, бан-лист, сообщения)
        └── commands.py         # Регистрация команд бота
```

---

## ⚙️ Команды бота

| Команда | Описание |
|---|---|
| `/start` | Главное меню |
| `/add_user` | Добавить пользователя в вайтлист *(только admin)* |
| `/remove_user` | Удалить пользователя из вайтлиста *(только admin)* |
| `/ban_seller` | Добавить продавца в чёрный список *(только admin)* |
| `/unban_seller` | Убрать продавца из чёрного списка *(только admin)* |

---

## 📄 Лицензия

[MIT](LICENSE)
