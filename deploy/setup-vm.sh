#!/usr/bin/env bash
# One-time setup of the Oracle Cloud Always Free ARM VM (Ubuntu 22.04/24.04 or Oracle Linux 9), run from the repo root:
#   bash deploy/setup-vm.sh
# Installs Docker, then starts the backbone. Fill in .env (copied from .env.example) before the second run.
set -euo pipefail

install_docker() {
  if command -v apt-get >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose-v2 git
  elif command -v dnf >/dev/null; then
    sudo dnf install -y dnf-plugins-core
    sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin git
    sudo systemctl enable --now docker
  else
    echo "Install Docker and docker compose, then re-run this script." >&2
    exit 1
  fi
  sudo usermod -aG docker "$USER"
  echo "Docker installed. Log out and back in (or: newgrp docker), then run this script again."
  exit 0
}

if ! command -v docker >/dev/null; then
  install_docker
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Fill it in, then run this script again."
  exit 1
fi

sudo docker compose -f deploy/compose.yaml --env-file .env up -d
sudo docker compose -f deploy/compose.yaml --env-file .env ps
