#!/bin/bash
# macOS launcher: only Docker Desktop is required on the host.
set -eu
SCRIPT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIRECTORY="$(cd -- "$SCRIPT_DIRECTORY/.." && pwd)"
cd "$PROJECT_DIRECTORY"
export PATH="/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

pause_on_exit() {
  launch_status=$?
  if [ "$launch_status" -ne 0 ]; then
    printf '\nЗапуск не завершён. Сообщение об ошибке находится выше.\n'
  fi
  if [ -t 0 ] && [ "${AGENTPASS_NO_PAUSE:-0}" != '1' ]; then
    printf '\nНажмите Enter, чтобы закрыть это окно.\n'
    IFS= read -r agentpass_answer || true
  fi
}
trap pause_on_exit EXIT

if ! command -v docker >/dev/null 2>&1; then
  printf '\nДля AgentPass нужен Docker Desktop. Node.js, npm и Python устанавливать не нужно.\n'
  printf 'Скачайте Docker Desktop: https://www.docker.com/products/docker-desktop/\n'
  printf 'Установите приложение, запустите его и снова откройте Start AgentPass.command.\n'
  if command -v open >/dev/null 2>&1; then
    open 'https://www.docker.com/products/docker-desktop/' || true
  fi
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  printf '\nНе найден Docker Compose v2. Обновите Docker Desktop и повторите запуск.\n'
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  printf '\nЗапускаю Docker Desktop…\n'
  if command -v open >/dev/null 2>&1; then
    open -a Docker || true
  fi
  docker_is_ready=0
  for ((attempt=0; attempt<90; attempt++)); do
    if docker info >/dev/null 2>&1; then
      docker_is_ready=1
      break
    fi
    sleep 1
  done
  if [ "$docker_is_ready" != '1' ]; then
    printf 'Откройте Docker Desktop, завершите его первоначальную настройку и повторите запуск.\n'
    exit 1
  fi
fi

if [ ! -f .env ]; then
  if ! command -v openssl >/dev/null 2>&1; then
    printf 'Не найден системный OpenSSL для создания ключа конфигурации.\n'
    exit 1
  fi
  umask 077
  encryption_value="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\r\n')"
  temporary_config="$(mktemp .env.XXXXXXXX)"
  printf '%s\n' \
    'ENVIRONMENT=sandbox' \
    'DATABASE_URL=postgresql+psycopg://agentpass:local-sandbox-only@localhost:5432/agentpass' \
    "ENCRYPTION_KEY=$encryption_value" \
    'SEED_DEMO=true' \
    'DEMO_PASSWORD=AgentPass-demo-2026!' \
    'WEB_ORIGIN=http://localhost:3000' \
    'COOKIE_SECURE=false' > "$temporary_config"
  mv "$temporary_config" .env
  unset encryption_value
  printf 'Создана локальная конфигурация.\n'
fi

launch_action="${1:-start}"
if [ "$launch_action" = 'stop' ]; then
  docker compose --env-file .env -f infra/compose.yml stop
  printf '\nAgentPass остановлен. Все данные сохранены.\n'
  exit 0
fi

printf '\nЗапускаю AgentPass. Первая сборка может занять несколько минут.\n'
if [ "${AGENTPASS_REUSE_IMAGES:-0}" = '1' ]; then
  docker compose --env-file .env -f infra/compose.yml up -d --wait --wait-timeout 120
else
  docker compose --env-file .env -f infra/compose.yml up --build -d --wait --wait-timeout 120
fi

web_port="${WEB_PORT:-$(sed -n 's/^WEB_PORT=//p' .env | tail -1 | tr -d '\r')}"
web_port="${web_port:-3000}"
web_url="http://localhost:$web_port"
site_is_ready=0
for ((attempt=0; attempt<45; attempt++)); do
  if curl --silent --fail --max-time 2 "$web_url/login" >/dev/null 2>&1; then
    site_is_ready=1
    break
  fi
  sleep 1
 done
if [ "$site_is_ready" != '1' ]; then
  printf 'Сайт ещё не ответил. Проверьте сообщения Docker выше.\n'
  exit 1
fi
printf '\nAgentPass работает: %s\n' "$web_url"
printf 'На странице входа нажмите «Открыть полный sandbox».\n'
printf 'Откроются все четыре интерфейса, включая Admin Console.\n'
if [ "${AGENTPASS_NO_BROWSER:-0}" != '1' ] && command -v open >/dev/null 2>&1; then
  open "$web_url" || true
fi
