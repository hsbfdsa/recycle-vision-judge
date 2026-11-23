#!/usr/bin/env bash
# Ubuntu EC2 첫 설정: 스왑, Docker 설치
#   사용: bash deploy/setup.sh
set -euo pipefail

# 1GB 메모리 서버에서 이미지 빌드가 멈추지 않게 2GB 스왑
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

echo
echo "완료. 로그아웃 후 다시 접속하면 sudo 없이 docker를 쓸 수 있습니다."
echo "다음: 저장소 루트에 .env 작성 → cd deploy && DOMAIN=<주소> docker compose up -d --build"
