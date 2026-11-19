#!/usr/bin/env bash
# Idempotent host setup for an Ubuntu GPU VM (Jarvislabs VM or on-prem):
# Docker + compose plugin, NVIDIA Container Toolkit, uv. Prints versions for check A3/A4.
set -euo pipefail
SUDO=""; [ "$(id -u)" = 0 ] || SUDO=sudo

nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | $SUDO sh
fi
if ! command -v nvidia-ctk >/dev/null; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | $SUDO gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    | $SUDO tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq nvidia-container-toolkit
fi
if ! $SUDO docker info --format '{{json .Runtimes}}' | grep -q nvidia; then
  $SUDO nvidia-ctk runtime configure --runtime=docker
  $SUDO systemctl restart docker
fi
if [ -n "$SUDO" ] && ! id -nG | grep -qw docker; then
  $SUDO usermod -aG docker "$USER"
  echo "added $USER to the docker group: log out and back in (or use 'sg docker')"
fi
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh

docker --version
docker compose version
nvidia-ctk --version | head -1
$SUDO docker info 2>/dev/null | grep -iE '^ *(default )?runtimes?:'
