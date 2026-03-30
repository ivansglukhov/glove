#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="${SERVICE_NAME:-glove-bot}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-$(git -C "${PROJECT_DIR}" rev-parse --abbrev-ref HEAD)}"
PYTHON_BIN="${PYTHON_BIN:-${PROJECT_DIR}/.venv/bin/python}"
PIP_BIN="${PIP_BIN:-${PROJECT_DIR}/.venv/bin/pip}"

cd "${PROJECT_DIR}"

if ! command -v git >/dev/null 2>&1; then
  echo "Не найден git."
  exit 1
fi

if [[ ! -d .git ]]; then
  echo "Каталог проекта не является git-репозиторием: ${PROJECT_DIR}"
  exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Не найден ${PYTHON_BIN}"
  echo "Сначала подготовьте окружение: bash debian/setup.sh"
  exit 1
fi

if [[ ! -x "${PIP_BIN}" ]]; then
  echo "Не найден ${PIP_BIN}"
  exit 1
fi

echo "[1/5] Проверка локальных изменений"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "В репозитории есть незакоммиченные изменения. Остановлено."
  exit 1
fi

echo "[2/5] Обновление git"
git fetch "${GIT_REMOTE}"
git pull --ff-only "${GIT_REMOTE}" "${GIT_BRANCH}"

echo "[3/5] Обновление зависимостей проекта"
"${PIP_BIN}" install -e .

echo "[4/5] Проверка сборки"
"${PYTHON_BIN}" -c "from bot.main import build_application; build_application(); print('build ok')"

echo "[5/5] Перезапуск сервиса ${SERVICE_NAME}"
if command -v sudo >/dev/null 2>&1; then
  sudo systemctl restart "${SERVICE_NAME}"
  sudo systemctl status "${SERVICE_NAME}" --no-pager
else
  systemctl restart "${SERVICE_NAME}"
  systemctl status "${SERVICE_NAME}" --no-pager
fi

echo
echo "Обновление завершено."
