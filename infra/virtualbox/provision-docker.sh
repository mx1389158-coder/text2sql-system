#!/bin/sh
set -eu

sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 ca-certificates curl
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
echo "Docker installed. Log out and back in before running docker compose."
