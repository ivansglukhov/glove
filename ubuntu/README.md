# Ubuntu Deployment

Этот каталог содержит минимальный комплект для запуска бота на Ubuntu.

## Что внутри

- `setup.sh` - первичная подготовка сервера и проекта
- `run.sh` - ручной запуск бота
- `install_systemd.sh` - установка и включение `systemd`-сервиса
- `glove-bot.service` - шаблон `systemd`-юнита

## Требования

- Ubuntu 24.04+ или любая Ubuntu, где уже установлен `python3.12`
- `BOT_TOKEN`
- `ADMIN_TELEGRAM_ID`

Проект требует `Python >= 3.12`. На Ubuntu 22.04 стандартный `python3` обычно слишком старый.

## Быстрый сценарий

### 1. Скопировать проект на сервер

Например:

```bash
sudo mkdir -p /opt/glove
sudo chown "$USER":"$USER" /opt/glove
rsync -av ./ /opt/glove/
```

### 2. Подготовить окружение

```bash
cd /opt/glove
bash ubuntu/setup.sh
```

По умолчанию скрипт ожидает `python3.12`. Если бинарь называется иначе:

```bash
PYTHON_BIN=/usr/bin/python3.12 bash ubuntu/setup.sh
```

### 3. Настроить `.env`

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

### 4. Если нужна текущая база

Скопировать `glove.sqlite3` в корень проекта:

```bash
scp glove.sqlite3 user@server:/opt/glove/glove.sqlite3
```

Если база не перенесена, бот создаст новую пустую при старте.

### 5. Проверить ручной запуск

```bash
cd /opt/glove
bash ubuntu/run.sh
```

Остановить можно `Ctrl+C`.

### 6. Поставить как сервис

```bash
cd /opt/glove
sudo bash ubuntu/install_systemd.sh
```

Потом проверить:

```bash
systemctl status glove-bot
journalctl -u glove-bot -f
```

## Что делает setup

- проверяет наличие `python3.12`
- создаёт `.venv`
- обновляет `pip`
- ставит проект через `pip install -e .`

## Что важно учесть

- Не запускайте одновременно несколько экземпляров бота с одной SQLite-базой.
- У пользователя сервиса должны быть права на запись в каталог проекта и в `glove.sqlite3`.
- Если переносите проект с Windows, проверьте, что файлы в UTF-8 и что у скриптов есть `LF`, а не только `CRLF`.
- При старте бот сам добавляет недостающие колонки в таблицу `mail_messages`, так что отдельной миграции для текущей схемы не нужно.

## Полезные команды

Перезапуск сервиса:

```bash
sudo systemctl restart glove-bot
```

Остановка:

```bash
sudo systemctl stop glove-bot
```

Запуск:

```bash
sudo systemctl start glove-bot
```

Логи:

```bash
journalctl -u glove-bot -n 200
```
