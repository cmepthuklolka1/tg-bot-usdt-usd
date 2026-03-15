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

### 2. Запустите скрипт установки

```bash
chmod +x install.sh
./install.sh
```

Скрипт автоматически:
- создаст виртуальное окружение и установит зависимости
- скопирует шаблоны конфигурационных файлов
- создаст файл службы systemd (`/etc/systemd/system/usdt-bot.service`)
- выведет команды для добавления в автозапуск

### 3. Заполните `.env`

```bash
nano .env
```

```env
BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_ID=ваш_telegram_id
```

<details>
<summary>🖥️ Установка на Windows</summary>

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Скопируйте конфигурационные файлы:

```bat
copy .env.example .env
copy config\whitelist.example.json config\whitelist.json
copy config\banned_sellers.example.json config\banned_sellers.json
copy config\pinned_messages.example.json config\pinned_messages.json
```

Отредактируйте `.env`:

```env
BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_ID=ваш_telegram_id
```

</details>

---

## ▶️ Запуск

```bash
python main.py
```

---

## 🔧 Управление службой (Linux)

```bash
# Добавить в автозапуск и запустить
sudo systemctl enable usdt-bot
sudo systemctl start usdt-bot

# Статус
sudo systemctl status usdt-bot

# Остановить / перезапустить
sudo systemctl stop usdt-bot
sudo systemctl restart usdt-bot

# Логи в реальном времени
sudo journalctl -u usdt-bot -f
```

<details>
<summary>🖥️ Управление службой на Windows (NSSM)</summary>

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

</details>

---

## 🔄 Обновление проекта

```bash
sudo systemctl stop usdt-bot
git pull origin master
venv/bin/pip install -r requirements.txt
sudo systemctl start usdt-bot
```

<details>
<summary>🖥️ Обновление на Windows</summary>

```bat
nssm stop USDTBot
git pull origin master
venv\Scripts\pip install -r requirements.txt
nssm start USDTBot
```

</details>

---

## 📁 Структура проекта

```
tg-bot-usdt-usd/
├── main.py                     # Точка входа + фоновое автообновление
├── install.sh                  # Скрипт установки для Linux
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
