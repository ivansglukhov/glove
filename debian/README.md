# Debian Deployment

Этот каталог содержит комплект для запуска бота на Debian с установкой Python 3.12 из исходников.

## Почему так

Проект требует `Python >= 3.12`. По данным Debian Packages:

- в `bookworm` пакет `python3` остаётся на ветке `3.11`
- пакет `python3.12` есть в `sid (unstable)`, но это не тот путь, который обычно хочется тянуть на стабильный сервер

Поэтому для Debian здесь используется отдельная локальная установка `Python 3.12.13` из исходников `python.org`.

Источники:

- Debian Packages, `python3` для `bookworm`: https://packages.debian.org/bookworm/python/python3
- Debian Packages, `python3.12` для `sid`: https://packages.debian.org/en/sid/python3.12
- Python 3.12.13 release: https://www.python.org/downloads/release/python-31213/

## Что внутри

- `install_python312.sh` - ставит системные зависимости и собирает Python 3.12.13 в `/opt/python-3.12`
- `setup.sh` - создаёт `.venv` и ставит проект
- `run.sh` - ручной запуск бота
- `update_from_git.sh` - подтягивает обновления из git и перезапускает `glove-bot`
- `install_systemd.sh` - установка `systemd`-сервиса
- `glove-bot.service` - шаблон `systemd`-юнита

## Проверенный сценарий

### 1. Скопировать проект на сервер

Например:

```bash
sudo mkdir -p /opt/glove
sudo chown "$USER":"$USER" /opt/glove
rsync -av ./ /opt/glove/
```

### 2. Установить Python 3.12

```bash
cd /opt/glove
sudo bash debian/install_python312.sh
```

По умолчанию Python будет установлен в:

```bash
/opt/python-3.12/bin/python3.12
```

### 3. Подготовить окружение проекта

```bash
cd /opt/glove
PYTHON_BIN=/opt/python-3.12/bin/python3.12 bash debian/setup.sh
```

### 4. Настроить `.env`

Если файла нет:

```bash
cp .env.example .env
```

Минимально нужно заполнить:

```env
BOT_TOKEN=...
ADMIN_TELEGRAM_ID=...
DATABASE_URL=sqlite:///glove.sqlite3
DEFAULT_ELO_RATING=1000
ELO_K_FACTOR=32
INVITATION_TTL_DAYS=7
MATCH_CONFIRM_TTL_DAYS=7
```

### 5. Если нужна текущая база

Скопировать `glove.sqlite3` в корень проекта:

```bash
scp glove.sqlite3 user@server:/opt/glove/glove.sqlite3
```

### 6. Проверить ручной запуск

```bash
cd /opt/glove
bash debian/run.sh
```

### 7. Поставить как сервис

```bash
cd /opt/glove
sudo bash debian/install_systemd.sh
```

Проверка:

```bash
systemctl status glove-bot
journalctl -u glove-bot -f
```

### 8. Обновление из git

Когда код уже на сервере и сервис установлен:

```bash
cd /opt/glove
bash debian/update_from_git.sh
```

Скрипт:

- проверяет, что рабочее дерево чистое
- делает `git fetch` и `git pull --ff-only`
- обновляет установленный проект через `pip install -e .`
- проверяет `build_application()`
- перезапускает `glove-bot` через `systemctl`

## Что делает install_python312.sh

- ставит системные пакеты для сборки Python
- скачивает Python 3.12.13 с `python.org`
- собирает и ставит его в `/opt/python-3.12`
- не заменяет системный `python3`

## Что важно

- Не запускайте два экземпляра бота одновременно на одной SQLite-базе.
- У пользователя сервиса должны быть права на запись в каталог проекта и `glove.sqlite3`.
- Скрипт ставит Python отдельно от системного, чтобы не ломать системные зависимости Debian.
- В проекте уже есть логирование в `logs/bot.log` с ротацией.

## Полезные команды

Проверить Python:

```bash
/opt/python-3.12/bin/python3.12 --version
```

Перезапуск сервиса:

```bash
sudo systemctl restart glove-bot
```

Логи:

```bash
journalctl -u glove-bot -n 200
tail -f /opt/glove/logs/bot.log
```
