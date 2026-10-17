# 💱 USDT/USD Rate Monitor Bot

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)](https://www.python.org/)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-blue)](https://docs.aiogram.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

Приватный Telegram-бот для мониторинга актуальных курсов USDT/RUB. Агрегирует данные из нескольких источников и автоматически обновляет закреплённое сообщение каждый час. Общие снимки источников разделяются между пользователями; временные сбои не удаляют закрепление.

---

## 📊 Источники данных

| Источник | Что парсим |
|---|---|
| **ЦБ РФ** | Официальный курс USD/RUB: прямой HTTPS-запрос и [зеркало CBR XML Daily](https://www.cbr-xml-daily.ru/) параллельно, первый корректный ответ |
| **ABCEX** | Последняя цена USDT/RUB на бирже |
| **Antarctic Wallet** | Курс пополнения USDT/RUB с обозначением cash / SBP / общего резерва |
| **BestChange.ru** | Топ обменников (2 таблицы с независимыми настройками) |
| **Bybit P2P** | Топ продавцов USDT за RUB (2 таблицы с независимыми настройками) |

---

## ✨ Функции

- 📌 Одно закреплённое сообщение с курсами, обновляемое на месте (не спамит чат)
- 📊 Кнопка «Курс USD/USDT» открывает отчёт на месте меню и закрепляет его; предыдущее закрепление снимается после успешного сохранения нового. Кнопка «Обновить» обновляет видимый отчёт.
- 🔄 Автообновление каждый час в фоне, отдельная проверка восстановления Antarctic каждые 60 секунд
- 🕒 Последний успешный курс при сбое с явным возрастом, дата курса ЦБ и время МСК
- ✅ Уведомление о восстановлении; сетевой таймаут не требует замены токенов
- ⚡ Ручное обновление по кнопке
- 🔒 Приватный доступ — только вайтлист пользователей
- 🚫 Фильтрация продавцов Bybit по чёрному списку
- 👑 Панель администратора для управления доступом и чёрным списком

---

## 🚀 Установка

Приложение устанавливается в `/opt/crypto-exkurs-bot` — стандартный каталог для стороннего ПО на Linux.

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
- скопирует файлы в `/opt/crypto-exkurs-bot` и настроит права доступа
- создаст виртуальное окружение и установит зависимости
- скопирует шаблоны конфигурационных файлов
- создаст файл службы systemd (`/etc/systemd/system/crypto-exkurs-bot.service`)
- выведет команды для добавления в автозапуск

> Если клонировать сразу в целевой каталог (`git clone <url> /opt/crypto-exkurs-bot`), шаг копирования пропускается автоматически.

### 3. Заполните `.env`

```bash
nano /opt/crypto-exkurs-bot/.env
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
sudo systemctl enable crypto-exkurs-bot
sudo systemctl start crypto-exkurs-bot

# Статус
sudo systemctl status crypto-exkurs-bot

# Остановить / перезапустить
sudo systemctl stop crypto-exkurs-bot
sudo systemctl restart crypto-exkurs-bot

# Логи в реальном времени
sudo journalctl -u crypto-exkurs-bot -f
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
bash /opt/crypto-exkurs-bot/deploy.sh
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

Бот может показывать курс продажи USDT/RUB с [Antarctic Wallet](https://app.antarcticwallet.com). Для этого нужны токены авторизации. Бот **автоматически обновляет** токены. Повторный вход нужен при подтверждённом отказе авторизации refresh token. Сетевой сбой или таймаут сами по себе не требуют повторного входа.

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

После первоначальной настройки бот **сам обновляет токены** за 24 часа до их истечения. Новые токены автоматически сохраняются в тот же файл. Если refresh token явно отклонён API, бот сообщит о необходимости повторного входа. При сетевой ошибке обновления бот повторит попытку автоматически и продолжит использовать действующий access token. Рабочий процесс подхватывает корректную замену файла токенов без перезапуска. Запись ротированной пары атомарна, права файла — 0600; при ошибке диска новая пара остаётся в памяти для повторного сохранения.

---

## 📁 Структура проекта

```
tg-bot-usdt-usd/          (исходный репозиторий)
/opt/crypto-exkurs-bot/            (установочный каталог на сервере)
├── main.py               # Точка входа + фоновое автообновление
├── install.sh            # Скрипт установки (копирует в /opt/crypto-exkurs-bot)
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


**Надёжность и настройки**

Python 3.12+; CI проверяет 3.12 и 3.14. Тесты не обращаются к рабочим API:

```bash
BOT_ENV_FILE=/dev/null python -m unittest discover -s tests -v
python -m pip check
```

Сумма в настройках Bybit — размер вашей сделки в рублях. Предложение должно удовлетворять `minAmount <= сумма <= maxAmount` и иметь достаточный объём USDT. Старые сохранённые суммы продолжают использоваться, фильтр стал учитывать полный диапазон.

Переменные окружения (можно добавить в `.env`):

| Переменная | По умолчанию | Назначение |
|---|---:|---|
| `FETCH_TIMEOUT` | 15 | Таймаут HTTP-запроса, секунды |
| `CONNECT_TIMEOUT` | 4 | Таймаут подключения |
| `FETCH_RETRIES` | 3 | Максимум попыток при временных ошибках |
| `SOURCE_TIMEOUT` | 40 | Общий бюджет одного источника с повторами и резервами |
| `REPORT_TIMEOUT` | 45 | Максимум ожидания источника при построении отчёта |
| `CACHE_TTL` | 30 | Общий кэш снимков, секунды |
| `MAX_STALE_SECONDS` | 3600 | Максимальный возраст последнего успешного значения при сбое |
| `RECOVERY_INTERVAL` | 60 | Проверка восстановления и обслуживание токенов |
| `NOTIFICATION_FAILURES` | 2 | Сколько проверок должно завершиться ошибкой до сетевого предупреждения |
| `NOTIFICATION_REMINDER` | 3600 | Интервал повторного предупреждения |
| `UPDATE_INTERVAL` | 3600 | Период фонового обновления отчётов |
| `MAX_HTTP_CLIENTS` | 6 | Ограничение одновременного сбора |

`config/runtime_state.json` хранит инциденты, `config/rate_cache.json` — последнее успешное значение и его время, `config/health.json` — свежесть процесса и источников. Эти файлы исключены из Git. При резервном общем курсе Antarctic отчёт явно пишет «общий buyRate (резерв)»; он не выдаётся за курс конкретного способа пополнения. Отключённый флагом cash onramp с работающим SBP считается штатным переключением.

Курс ЦБ запрашивается одновременно с `https://www.cbr.ru/scripts/XML_daily.asp` и `https://www.cbr-xml-daily.ru/daily_utf8.xml`. Используется первый успешно проверенный ответ с датой курса и положительным конечным USD/RUB с учётом номинала валюты. Ошибка одного адреса не прерывает второй запрос; сетевые сбои повторяются независимо в пределах `SOURCE_TIMEOUT`. После успеха или отмены оставшиеся запросы отменяются с ожиданием завершения. Если оба адреса недоступны, применяется общая политика последнего успешного курса с явным возрастом. Выбранный адрес отмечается в журнале полем `source=cbrf endpoint=direct|mirror event=selected`.

Сетевое предупреждение отправляется после порога, затем не чаще интервала напоминания. Подтверждённая ошибка авторизации, конфигурации или сохранения токенов требует отдельного действия. После восстановления приходит одно сообщение с длительностью сбоя. Состояние сохраняется между перезапусками. Недоставленные уведомления повторяются при следующей проверке.

**Обновление и откат**

`deploy.sh` загружает refs из GitHub, но не меняет работающий venv. Для новой ревизии создаётся `.releases/<SHA>` со своим venv. Сначала выполняются тесты на тестовой конфигурации и `pip check`, затем подключаются общие `.env`/`config` и переключается systemd override. При неудачной проверке нового PID, SHA, heartbeat и свежих данных автоматически восстанавливается прежний override и служба.

```bash
# Подготовить и проверить кандидата, не переключая службу
bash /opt/crypto-exkurs-bot/deploy.sh --prepare-only

# Проверить и активировать конкретный commit
bash /opt/crypto-exkurs-bot/deploy.sh --ref <commit-SHA>
```

По умолчанию обновляется upstream текущей ветки; параметр `--ref` позволяет выбрать точный SHA. Перед развёртыванием отслеживаемые файлы должны быть чистыми. Внешние секреты не входят в архив релиза и не копируются в тестовое окружение. Изменение unit требует sudo. Релизы сохраняются для диагностики; для ручного возврата можно активировать ранее подготовленный SHA той же командой. На первом переходе со старой версии репозитория требуется установить новый `scripts/release.py`/`deploy.sh` из проверенной ревизии.

Секреты `.env` и `config/antarctic_tokens.json` должны принадлежать пользователю службы и иметь права 0600. Не помещайте GitHub PAT в remote URL. Для публичного репозитория достаточно обычного HTTPS URL, для приватного используйте ключ репозитория только на чтение. Уже раскрытый PAT необходимо отозвать в настройках GitHub; удаления из `.git/config` недостаточно для отзыва ключа.
