# AgentPass

[![AgentPass CI](https://github.com/shevelevmotya/agentpass/actions/workflows/ci.yml/badge.svg)](https://github.com/shevelevmotya/agentpass/actions/workflows/ci.yml)

Платформа контроля финансовых полномочий AI-агентов: мандаты, лимиты,
детерминированные APPROVE / ASK_USER / DENY, одноразовое согласие,
подписанное разрешение на исполнение, аудит и платёжная песочница.

## Материалы решения

| Материал | Файл |
|---|---|
| Презентация, 10 слайдов | [PDF](submission/AgentPass_Presentation.pdf) · [PPTX](submission/AgentPass_Presentation.pptx) |
| Видео работающей песочницы, 3 минуты | [MP4](submission/AgentPass_Demo.mp4) |
| Рынок, продуктовые гипотезы и результаты проверки | [Отчёт](submission/AgentPass_Analytics.pdf) · [Архив аналитики](submission/AgentPass_Analytics.zip) |
| Финансовая модель: 3 сценария, все вводные — гипотезы | [XLSX](submission/AgentPass_Financial_Model.xlsx) |
| Гайды и рабочая книга исследования | [Customer discovery](submission/AgentPass_Customer_Discovery.pdf) · [XLSX](submission/AgentPass_Research_Workbook.xlsx) |
| 10 интервью с ИИ-респондентами, роли подписаны | [Общий PDF](submission/AgentPass_Interviews.pdf) · [Протоколы](submission/AgentPass_AI_Panel.zip) |
| Короткий питч и вопросы жюри | [Текст](submission/AgentPass_Pitch_3min.txt) · [Вопросы и ответы](submission/AgentPass_Jury_Questions.pdf) |

[Каталог материалов](submission/README.md) · [Скачать комплект в Releases](https://github.com/shevelevmotya/agentpass/releases).
Реальных клиентских интервью и подтверждённых продаж нет. Ролевые ответы ИИ
выделены отдельно и не считаются доказательством спроса или готовности платить.

## Запуск

На Mac нужен Docker Desktop. Откройте Start AgentPass.command в папке проекта.
Сайт: http://localhost:3000. Для остановки — Stop AgentPass.command.
Первый запуск загружает зависимости и может занять несколько минут.

Из терминала с Python: python3 infra/run.py
Ручной Compose: python3 infra/bootstrap.py, затем
docker compose --env-file .env -f infra/compose.yml up --build -d

На странице входа нажмите «Открыть полный sandbox». Для локального запуска
используется штатная серверная авторизация. Сервис не развёрнут как публичная
платёжная инфраструктура; материалы на GitHub доступны для ознакомления.

## Стек и компоненты

Next.js / TypeScript, FastAPI / SQLAlchemy / Alembic, PostgreSQL 16,
TypeScript SDK, Docker Compose, pytest, Playwright, GitHub Actions.
User Dashboard, Developer Portal, Agent Console, Admin Console.

## Демонстрация

Войти «Открыть полный sandbox», в Agent Console создать новый демо-бюджет.
8 000 ₽ — APPROVE; 12 000 ₽ — ASK с подтверждением; 18 000 ₽ — DENY.
Сценарии обращаются к одному backend и Policy Engine.

## Проверки

Перед публикацией 01.11.2026 на отдельной PostgreSQL базе заново пройдены
114 pytest, strict typecheck и production build. Предыдущая проверка
30.10.2026 также включала 8 Playwright, 14 HTTP smoke и 16 execution SDK checks.
Удалённые проверки и их актуальный результат доступны в GitHub Actions.
Команды: pytest apps/api/tests -q; npm run typecheck; npm run build;
npm run test:e2e; python infra/smoke.py; python infra/verify-pilot-sdk.py.
Backend-команды требуют Python 3.12, PYTHONPATH=apps/api, зависимостей
apps/api/requirements.lock и отдельной мигрированной БД *_test для pytest.

## Документация

[Архитектура](ARCHITECTURE.md) · [API](API.md) · [Модель данных](DATA_MODEL.md) ·
[Безопасность](SECURITY.md) · [Демо](DEMO.md) · [Эксплуатация](docs/OPERATIONS.md) ·
[Платёжная песочница](docs/PAYMENT_SANDBOX.md) ·
[Внешний агент](examples/external-agent/README.md) ·
[Пакет банковского пилота](docs/bank-pilot/01-executive-technical-summary.md).

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
