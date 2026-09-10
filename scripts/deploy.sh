#!/usr/bin/env bash
# GCP VM 배포 스크립트. CD 워크플로우(self-hosted runner)와 수동 실행 양쪽에서 쓴다.
#
#   ./scripts/deploy.sh          # api 만
#   DEPLOY_SERVICES="api frontend" ./scripts/deploy.sh
set -euo pipefail

COMPOSE_FILE="docker/docker-compose.yml"
SERVICES="${DEPLOY_SERVICES:-api}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"

cd "$(dirname "$0")/.."

echo "▶ 배포 커밋: $(git rev-parse --short HEAD)"

echo "▶ 빌드 + 기동: $SERVICES"
docker compose -f "$COMPOSE_FILE" up -d --build --remove-orphans $SERVICES

echo "▶ 헬스체크: $HEALTH_URL"
for i in $(seq 1 "$HEALTH_RETRIES"); do
  if curl -fsS -o /dev/null "$HEALTH_URL"; then
    echo "✓ healthy ($i 회차)"
    break
  fi
  if [ "$i" -eq "$HEALTH_RETRIES" ]; then
    echo "✗ 헬스체크 실패. 로그:"
    docker compose -f "$COMPOSE_FILE" logs --tail=50 api
    exit 1
  fi
  sleep 2
done

echo "▶ 미사용 이미지 정리"
docker image prune -f >/dev/null

echo "✓ 배포 완료: $(git rev-parse --short HEAD)"
docker compose -f "$COMPOSE_FILE" ps
