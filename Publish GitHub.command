#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIRECTORY"
if ! command -v gh >/dev/null 2>&1; then
  printf 'Установите GitHub CLI: https://cli.github.com/\n'
  exit 1
fi
if ! LOGIN="$(gh api user --jq .login)" || [ -z "$LOGIN" ]; then
  printf 'Выполните gh auth login --scopes repo,workflow и повторите запуск.\n'
  exit 1
fi
REPOSITORY_NAME="${1:-agentpass}"
case "$REPOSITORY_NAME" in *[!A-Za-z0-9_.-]*|'') printf 'Некорректное имя репозитория\n'; exit 1;; esac
REPOSITORY="$LOGIN/$REPOSITORY_NAME"
if gh repo view "$REPOSITORY" >/dev/null 2>&1; then
  printf 'Репозиторий %s уже существует. Скрипт не будет его менять. Передайте другое имя.\n' "$REPOSITORY"
  exit 1
fi
if [ -d .git ]; then
  printf 'Найдена существующая Git-история. Используйте свежую распакованную копию ZIP.\n'
  exit 1
fi
umask 077
cat > README.md <<'AGENTPASS_README'
# AgentPass

Платформа контроля финансовых полномочий AI-агентов: мандаты, лимиты,
детерминированные APPROVE / ASK_USER / DENY, одноразовое согласие,
подписанное разрешение на исполнение, аудит и платёжная песочница.

## Запуск

На Mac нужен Docker Desktop. Откройте Start AgentPass.command в папке проекта.
Сайт: http://localhost:3000. Для остановки — Stop AgentPass.command.
Первый запуск загружает зависимости и может занять несколько минут.

Из терминала с Python: python3 infra/run.py
Ручной Compose: python3 infra/bootstrap.py, затем
docker compose --env-file .env -f infra/compose.yml up --build -d

## Стек и компоненты

Next.js / TypeScript, FastAPI / SQLAlchemy / Alembic, PostgreSQL 16,
TypeScript SDK, Docker Compose, pytest, Playwright, GitHub Actions.
User Dashboard, Developer Portal, Agent Console, Admin Console.

## Демонстрация

Войти «Открыть полный sandbox», в Agent Console создать новый демо-бюджет.
8 000 ₽ — APPROVE; 12 000 ₽ — ASK с подтверждением; 18 000 ₽ — DENY.
Сценарии обращаются к одному backend и Policy Engine.

## Проверки

Проверено 30.10.2026: 114 pytest, 8 Playwright, strict typecheck и build.
HTTP smoke: 14 проверок; execution SDK: 16 проверок.
Команды: pytest apps/api/tests -q; npm run typecheck; npm run build;
npm run test:e2e; python infra/smoke.py; python infra/verify-pilot-sdk.py.
Backend-команды требуют Python 3.12, PYTHONPATH=apps/api, зависимостей
apps/api/requirements.lock и отдельной мигрированной БД *_test для pytest.

## Границы

Это локальный sandbox без реальных списаний и карточных данных.
Local simulator работает. Адаптер стандартного TEST checkout ЮKassa
подготовлен и покрыт mock/contract tests; внешнее соединение NOT VERIFIED.
Полный enterprise SSO, RLS, WORM, HA/DR и независимый security audit
не завершены. Банковского подключения и подтверждённых клиентов нет.
Демо-пароли разрешены только в локальном sandbox; pilot fail-closed
требует отдельной безопасной конфигурации, DB роли, HTTPS и MFA.

## Права

Права на AgentPass сохраняются у владельцев проекта. Публичное размещение
кода предназначено для технического ознакомления; условия коммерческого
использования и внедрения согласуются отдельно. Зависимости сохраняют
свои лицензии. Публикация не означает передачу исключительных прав.
AGENTPASS_README
git init -b main
git config user.name "$LOGIN"
git config user.email "$LOGIN@users.noreply.github.com"
git add .
git commit -m "AgentPass: financial authority control platform and sandbox"
gh repo create "$REPOSITORY" --public --source=. --remote=origin --push --description "Financial authority control for AI agents: mandates, policy decisions, approvals and execution grants"
gh repo view "$REPOSITORY" --json url --jq .url
printf '\nРепозиторий опубликован. Вставьте выведенную ссылку в поле исходного кода.\n'
