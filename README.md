# 💱 USDT/USD Rate Monitor Bot

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-blue)](https://docs.aiogram.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

Приватный Telegram-бот для мониторинга актуальных курсов USDT/RUB. Агрегирует данные из нескольких источников и автоматически обновляет закреплённое сообщение каждый час.

---

## 📊 Источники данных

| Источник | Что парсим |
|---|---|
| **ЦБ РФ** | Официальный курс USD/RUB |
| **ABCEX** | Последняя цена USDT/RUB на бирже |
| **Antarctic Wallet** | Курс продажи USDT/RUB |
| **BestChange.ru** | Топ обменников (2 таблицы с независимыми настройками) |
| **Bybit P2P** | Топ продавцов USDT за RUB (2 таблицы с независимыми настройками) |

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

Приложение устанавливается в `/opt/usdt-bot` — стандартный каталог для стороннего ПО на Linux.

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
- скопирует файлы в `/opt/usdt-bot` и настроит права доступа
- создаст виртуальное окружение и установит зависимости
- скопирует шаблоны конфигурационных файлов
- создаст файл службы systemd (`/etc/systemd/system/usdt-bot.service`)
- выведет команды для добавления в автозапуск

> Если клонировать сразу в целевой каталог (`git clone <url> /opt/usdt-bot`), шаг копирования пропускается автоматически.

### 3. Заполните `.env`

```bash
nano /opt/usdt-bot/.env
```

```env
BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_ID=ваш_telegram_id
```

### 4. Настройте Antarctic Wallet (опционально)

Для получения курса USDT/RUB с Antarctic Wallet нужно создать файл с токенами авторизации.
Подробная инструкция — в разделе [🔑 Настройка Antarctic Wallet](#-настройка-antarctic-wallet).

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
bash /opt/usdt-bot/deploy.sh
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

## 🔑 Настройка Antarctic Wallet

Бот может показывать курс продажи USDT/RUB с [Antarctic Wallet](https://app.antarcticwallet.com). Для этого нужны токены авторизации. Бот **автоматически обновляет** токены — вручную это нужно сделать только один раз (и повторить, если бот был выключен более 5 дней).

### Шаг 1. Авторизуйтесь на сайте

Откройте в браузере Chrome: `https://app.antarcticwallet.com/home` и войдите в аккаунт.

### Шаг 2. Получите токены

#### Способ A — Быстрый (через консоль браузера)

1. На странице Antarctic Wallet нажмите **F12** (откроются DevTools)
2. Перейдите на вкладку **Console**
3. Вставьте эту команду и нажмите Enter:

```js
JSON.stringify((()=>{const d=Object.keys(localStorage).map(k=>{try{const v=JSON.parse(localStorage.getItem(k));if(v?.state?.jwt?.accessToken)return v.state.jwt}catch{}return null}).find(Boolean);return d?{access_token:d.accessToken,refresh_token:d.refreshToken}:"Токены не найдены"})(),null,2)
```

4. Скопируйте результат — это готовый JSON с обоими токенами

#### Способ B — Ручной (через DevTools)

1. На странице Antarctic Wallet нажмите **F12** (откроются DevTools)
2. Перейдите на вкладку **Application**
3. В левой панели: **Local Storage** → `https://app.antarcticwallet.com`
4. В таблице справа найдите ключ, содержащий данные авторизации (обычно это Pinia-стор)
5. Кликните на него — в значении будет JSON-объект
6. Найдите внутри объект `jwt` с полями:
   - `accessToken` — длинная строка (начинается с `eyJ...`)
   - `refreshToken` — короткая hex-строка (32 символа)

### Шаг 3. Создайте файл токенов

Создайте файл `config/antarctic_tokens.json` в корне проекта:

```bash
nano config/antarctic_tokens.json
```

Вставьте данные в формате:

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiJ9.eyJ1c2Vy...(ваш длинный токен)",
  "refresh_token": "a1b2c3d4e5f6...(ваш 32-символьный токен)"
}
```

### Автообновление

После первоначальной настройки бот **сам обновляет токены** за 24 часа до их истечения. Новые токены автоматически сохраняются в тот же файл. Если бот был выключен более 5 дней и токены протухли — бот отправит администратору уведомление в Telegram, и процедуру нужно повторить.

---

## 📁 Структура проекта

```
tg-bot-usdt-usd/          (исходный репозиторий)
/opt/usdt-bot/            (установочный каталог на сервере)
├── main.py               # Точка входа + фоновое автообновление
├── install.sh            # Скрипт установки (копирует в /opt/usdt-bot)
├── deploy.sh             # Скрипт обновления (git pull + restart)
├── requirements.txt
├── .env.example          # Шаблон переменных окружения
├── config/
│   ├── whitelist.example.json
│   ├── banned_sellers.example.json
│   ├── pinned_messages.example.json
│   └── antarctic_tokens.json  # Токены Antarctic Wallet (создаётся вручную)
├── scripts/
│   ├── test_abcex.py
│   ├── test_antarctic.py
│   ├── test_antarctic_refresh.py
│   └── test_uniswap_owb.py
└── src/
    ├── config.py
    ├── domain/
    │   └── models.py
    ├── handlers/
    │   ├── user.py
    │   └── admin.py
    ├── keyboards/
    │   └── menus.py
    ├── services/
    │   ├── cbrf.py
    │   ├── abcex.py
    │   ├── antarctic.py
    │   ├── bestchange.py
    │   ├── bybit_p2p.py
    │   └── uniswap.py
    └── utils/
        ├── storage.py
        ├── retry.py      # Общие retry-декораторы для сервисов
        └── commands.py
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
