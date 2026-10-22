# Локальная разработка

Реализована основа FOUNDATION-01: API, стартовый React-экран, PostgreSQL, отдельный
мигратор и nginx. IDENTITY-01 добавляет вход сотрудников, сессии и роли; посетитель не регистрируется.
Все команды ниже выполняются из корня AsHana, если не указана другая папка.

## Запуск Docker

Нужны Docker Engine/Desktop и Compose v2 с поддержкой `--wait`.
Создайте локальный `.env` по `.env.example` самостоятельно и замените три заглушки
разными случайными паролями. Не передавайте этот файл агентам и не публикуйте его.

```sh
docker compose config --quiet
docker compose up --build --detach --wait --wait-timeout 180
```

Web: `http://127.0.0.1:8080`, API: `http://127.0.0.1:8000/api/v1/health/live`,
readiness: `http://127.0.0.1:8000/api/v1/health/ready`.
Документация API: `http://127.0.0.1:8000/api/docs`.
Порты web/API можно переопределить в `.env`; PostgreSQL наружу не публикуется.

Порядок: готовая db → успешный migrate → здоровый api → web.
Мигратор — отдельный контейнер с кодом завершения 0; он не должен постоянно работать.
Оба Python-контейнера используют один Dockerfile, но Compose даёт им разные image names,
чтобы параллельный build не записывал один tag одновременно.

```sh
docker compose ps --all
docker compose run --rm migrate
docker compose down
```

`down` сохраняет volume. Не выполнять `down -v` или удаление volumes без разрешения.
Init-script с ролями выполняется только для пустого volume. Изменение пароля в `.env`
не меняет пароль роли в уже созданной БД: нужна отдельная согласованная ротация.
Init-script включён в PostgreSQL image; его исполнение не зависит от прав host bind-mount.
Не печатать полный `compose config`, окружение контейнеров или реальные настройки.

## Локальные инструменты

Python 3.13, uv 0.13.3, Node 22.22.2, pnpm 10.34.7.
Версии пакетов закреплены lockfiles; не заменять их другим package manager.

```sh
cd backend
uv sync --frozen
uv run --frozen ruff check src tests migrations ../scripts
uv run --frozen ruff format --check src tests migrations ../scripts
uv run --frozen mypy
uv run --frozen pytest
```

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm format:check
pnpm typecheck
pnpm test
pnpm build
pnpm dev
```

Vite слушает localhost:5173 и проксирует `/api` на localhost:8000.
Для него можно запустить `docker compose up --build --detach --wait api`.
Собранный Docker web и Vite — разные способы просмотра одного приложения.
В `.tools/` могут находиться локально установленные инструменты сеанса; это
игнорируемый кеш, он не нужен пользователям с установленными uv/pnpm.

## Контракт API

Экспорт не запускает lifespan, не требует пароля БД и не читает `.env`.

```sh
cd backend
uv run --frozen python ../scripts/export_openapi.py
cd ../frontend
pnpm api:generate
```

После изменения HTTP-контракта обновить `backend/openapi.json` и
`frontend/src/shared/api/schema.d.ts`, проверить TypeScript.
Внешний JSON проверяется во время выполнения; типы не заменяют такую проверку.

## Полная проверка изолированного окружения

```sh
cd frontend
pnpm exec playwright install chromium
cd ..
python3 scripts/check_foundation.py --identity --web-port 18081 --api-port 18001
```

Нужны доступ к Docker, registries, установленный pnpm и свободные порты, выбранные через --web-port/--api-port (по умолчанию 18080/18000).
Скрипт игнорирует `.env`, генерирует временные случайные пароли в памяти процесса
и создаёт отдельный Compose project. Он проверяет новый volume, переход 0001 → 0002 → 0003 и повторный upgrade,
права runtime-роли, отказ/восстановление БД и API, затем запускает Playwright.
После проверки контейнеры и сеть удаляются, volume остаётся. Имена проекта выводятся
для последующей ручной очистки с разрешения владельца.

`--identity` дополнительно собирает test-stage, запускает PostgreSQL integration и передаёт
случайный временный пароль browser-тесту через окружение. Эти тесты требуют свежую БД;
их не следует запускать в рабочей базе. Тестовые номера синтетические, SMS не отправляется.
Auth-тесты не записывают traces, видео и screenshots с учётными данными.
`--skip-browser` исключает только браузерную часть.
`--keep-running` после успешной проверки оставляет стенд на localhost:18080 для просмотра.
Это временный стенд: пароли не сохраняются в `.env`, используйте обычный запуск выше
для постоянной разработки. Для остановки временного стенда можно выполнить
`docker stop <project>-web-1 <project>-api-1 <project>-db-1`, подставив выведенное имя.
Не перезапускайте скрипт на занятых портах без остановки предыдущего стенда.

Локальные screenshots/traces: `frontend/test-results/`, каталог игнорируется.
Playwright по умолчанию проверяет localhost:8080; `ASHANA_E2E_URL` задаёт другой локальный URL.

## Границы

Это локальный scaffold, не production-конфигурация: HTTPS, backup/restore, внешний onboarding, rate limits бизнес-операций и эксплуатационные настройки ещё впереди.
Mock-оплата не включена. В БД есть identity-таблицы; склад, заказы и платежи ещё не реализованы.
Базовые Docker images используют ветки версий; точный digest не закреплён.
См. [ADR-0006](../architecture/decisions/0006-local-foundation.md).

## Первый администратор и вход

На обычном локальном стенде после миграций выполните:

```sh
docker compose exec api python -m ashana.bootstrap.admin
```

CLI запрашивает имя, логин, необязательный мобильный KZ-номер и пароль с подтверждением; пароль не отображается.
Он не передаётся аргументом команды и не сохраняется в исходниках. Bootstrap работает
только local/test при demo_identity=true и при отсутствии admin. Повторное создание запрещено.
Откройте `/staff`, войдите и создайте сотрудников. Посетители пользуются главной без аккаунта.
На временном автоматическом тестовом стенде admin уже создан со случайным неизвестным
пользователю паролем; для собственного admin используйте отдельный обычный локальный стенд.

UI-01: вход и поиск сотрудников по login; телефон только для связи. Тестовый скрипт
с флагом --identity добавляет синтетическую запись перед 0003 и проверяет сохранение UUID,
парольного hash, контакта, ролей и сессии. У существующих аккаунтов login = staff_ + UUID
без дефисов; перед обновлением рабочего стенда оператор сообщает новые логины сотрудникам.

## Склад INVENTORY-01

После upgrade до 0004_inventory откройте `/staff/inventory` под manager/storekeeper.
[Порядок работы](inventory-usage.md). Полный изолированный прогон `--identity` теперь
включает inventory integration/E2E; он создаёт только синтетические партии в новой БД.

## Производство PRODUCTION-01

`/staff/production`: kitchen/manager. Сначала создать позиции и приход сырья на складе,
затем рецепт и выпуск по [инструкции](production-usage.md). Миграция 0005_production применяется
отдельным migrate; старые данные identity/inventory сохраняются. Проверка `--identity` в
scripts/check_foundation.py включает и production-тесты, временные cook.tests/cook.ui создаются
только в изолированной тестовой базе. Их пароли случайные и не предназначены для входа на основной стенд.

## Меню CATALOG-01

После upgrade до 0006_catalog: публичное меню `/`, управление `/staff/catalog` (manager).
Миграция сохраняет существующие аккаунты, склад и рецепты. Тестовые карточки/цены
не создаются на пользовательском стенде. [Порядок публикации](catalog-usage.md).

ORDERS-01: актуальная схема 0007_orders. Гостевые `/orders`, рабочие `/staff/orders`;
настройки в .env.example: cutoff оплаты 15 минут, полный резерв 300 секунд.
Оформление в слот закрывается за cutoff + TTL (по умолчанию 20 минут до получения).
Изменения окружения вступают в силу после пересоздания API. Telegram отключён при пустой
конфигурации; [подключение и ограничения](orders-usage.md).
