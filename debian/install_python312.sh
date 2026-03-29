#!/usr/bin/env bash
set -euo pipefail

PYTHON_VERSION="${PYTHON_VERSION:-3.12.13}"
PYTHON_PREFIX="${PYTHON_PREFIX:-/opt/python-3.12}"
BUILD_DIR="${BUILD_DIR:-/usr/local/src}"
ARCHIVE_NAME="Python-${PYTHON_VERSION}.tar.xz"
SOURCE_DIR="Python-${PYTHON_VERSION}"
DOWNLOAD_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/${ARCHIVE_NAME}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Запустите скрипт через sudo:"
  echo "  sudo bash debian/install_python312.sh"
  exit 1
fi

echo "[1/6] Установка пакетов для сборки"
apt update
apt install -y \
  build-essential \
  wget \
  curl \
  ca-certificates \
  libssl-dev \
  zlib1g-dev \
  libbz2-dev \
  libreadline-dev \
  libsqlite3-dev \
  libncursesw5-dev \
  xz-utils \
  tk-dev \
  libxml2-dev \
  libxmlsec1-dev \
  libffi-dev \
  liblzma-dev \
  libgdbm-dev \
  libnss3-dev \
  uuid-dev

mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"

echo "[2/6] Загрузка Python ${PYTHON_VERSION}"
rm -f "${ARCHIVE_NAME}"
wget -O "${ARCHIVE_NAME}" "${DOWNLOAD_URL}"

echo "[3/6] Распаковка"
rm -rf "${SOURCE_DIR}"
tar -xf "${ARCHIVE_NAME}"
cd "${SOURCE_DIR}"

echo "[4/6] Конфигурация"
./configure --prefix="${PYTHON_PREFIX}" --enable-optimizations --with-ensurepip=install

echo "[5/6] Сборка"
make -j"$(nproc)"

echo "[6/6] Установка"
make altinstall

echo
echo "Готово:"
echo "  ${PYTHON_PREFIX}/bin/python3.12 --version"
