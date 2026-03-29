#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="glove-bot.service"
SERVICE_SOURCE="${PROJECT_DIR}/ubuntu/${SERVICE_NAME}"
SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}"
SERVICE_USER="${SUDO_USER:-$USER}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Запустите скрипт через sudo:"
  echo "  sudo bash ubuntu/install_systemd.sh"
  exit 1
fi

if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
  echo "Не найден ${PROJECT_DIR}/.env"
  echo "Сначала создайте .env."
  exit 1
fi

if [[ ! -x "${PROJECT_DIR}/.venv/bin/python" ]]; then
  echo "Не найдено ${PROJECT_DIR}/.venv/bin/python"
  echo "Сначала выполните: bash ubuntu/setup.sh"
  exit 1
fi

sed \
  -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
  -e "s|__SERVICE_USER__|${SERVICE_USER}|g" \
  "${SERVICE_SOURCE}" > "${SERVICE_TARGET}"

systemctl daemon-reload
systemctl enable glove-bot
systemctl restart glove-bot

echo "Сервис установлен: ${SERVICE_TARGET}"
echo "Проверить статус:"
echo "  systemctl status glove-bot"
