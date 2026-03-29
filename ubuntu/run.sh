#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${PROJECT_DIR}"

if [[ ! -x .venv/bin/python ]]; then
  echo "Не найдено виртуальное окружение .venv."
  echo "Сначала выполните: bash ubuntu/setup.sh"
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "Не найден файл .env."
  echo "Создайте его на основе .env.example"
  exit 1
fi

exec .venv/bin/python -m bot.main
