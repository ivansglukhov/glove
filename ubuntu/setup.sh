#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

echo "[1/5] Проверка Python: ${PYTHON_BIN}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Не найден ${PYTHON_BIN}."
  echo "Установите Python 3.12 и python3.12-venv, затем повторите."
  exit 1
fi

echo "[2/5] Проверка версии Python"
"${PYTHON_BIN}" - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Нужен Python 3.12+")
print(f"OK: Python {sys.version.split()[0]}")
PY

cd "${PROJECT_DIR}"

echo "[3/5] Создание виртуального окружения"
"${PYTHON_BIN}" -m venv .venv

echo "[4/5] Обновление pip"
.venv/bin/python -m pip install --upgrade pip

echo "[5/5] Установка проекта"
.venv/bin/pip install -e .

if [[ ! -f .env ]]; then
  echo
  echo "Файл .env не найден."
  echo "Создайте его на основе .env.example:"
  echo "  cp .env.example .env"
fi

echo
echo "Готово."
echo "Ручной запуск:"
echo "  bash ubuntu/run.sh"
