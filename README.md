# AsHana

Система предварительного заказа еды и учёта столовой в Казахстане.

**Состояние на 23.10.2026:** реализованы гостевое меню и предзаказ с тестовой оплатой, выдача по
QR-коду, склад с партиями и накладными, рецепты и производство, касса с возвратами, долги
поставщикам, отчёты, живые экраны кухни, кассы и гостя (WebSocket), фото блюд, финансы месяца
и зарплата сотрудников, резервные копии. Оплата остаётся mock по решению владельца.
Telegram ждёт токен бота; пилот в реальной столовой не проводился. Подробно —
[текущий этап](tasks/current-sprint.md) и [backlog](tasks/backlog.md).

**Запуск на новом компьютере — [быстрый старт](docs/engineering/quick-start.md).**

Это самостоятельный проект, не модуль SSS Platform.

Подтверждено владельцем: Python + FastAPI; React + TypeScript; PostgreSQL; Docker;
Clean Architecture; русский интерфейс; важные комментарии на английском;
адаптивность; светлая и тёмная темы; переключатель видимости пароля; mock-оплата.

Начать с [AGENTS.md](AGENTS.md), затем [карты документов](docs/README.md),
[требований](docs/product/requirements.md) и [текущего этапа](tasks/current-sprint.md).
[Открытые вопросы](docs/open-questions.md) отделены от подтверждённых требований.

## Рабочая папка

Корневая папка репозитория AsHana (сейчас `/Users/abbos/Desktop/AsHana`; путь зависит от машины). Для дальнейшей разработки откройте именно эту папку
как проект в редакторе/Codex: текущий чат может оставаться привязанным к другой папке.
Не менять SSS Platform при работе над AsHana.

## Конфиденциальность

Агенты не выполняют commit/push/pull/merge, создание remote и PR без явной просьбы владельца.
Документация и инструкции могут быть на GitHub (решение 23.10.2026); `.env`, `secret/`,
дампы, резервные копии и отчёты тестов не публикуются — они в `.gitignore`.
[Политика](docs/engineering/privacy-and-git.md) обязательна для всех агентов.

## Запуск

Пошагово с GitHub — [quick-start.md](docs/engineering/quick-start.md). Кратко: создайте локальный `.env` по `.env.example` и самостоятельно замените три заглушки
разными случайными паролями. Затем:

```sh
docker compose up --build --detach --wait --wait-timeout 180
```

Откройте `http://127.0.0.1:8080`. Инструкция запуска, остановки без удаления данных,
локальных проверок и работы с временным стендом:
[local-development.md](docs/engineering/local-development.md).

Для первого сотрудника: `docker compose exec api python -m ashana.bootstrap.admin`.
После создания администратора откройте `/admin` (адрес кабинета сотрудников; ссылки на сайте нет). Пароля по умолчанию нет; используется
логин и пароль от администратора. Телефон необязателен и нужен только для связи. Реальные SMS и восстановление пока не подключены.

Склад: `/staff/inventory`, нужен manager/storekeeper. [Инструкция](docs/engineering/inventory-usage.md).

Производство: `/staff/production`, нужен kitchen/manager. [Инструкция](docs/engineering/production-usage.md).

Меню для посетителя: `/`. Управление: `/staff/catalog`, нужен manager.
[Инструкция](docs/engineering/catalog-usage.md).

Заказы гостя и QR-код: `/orders`. Заказы сотрудников и слоты: `/staff/orders`, выдача по QR: `/staff/scan`.
[Порядок оформления, оплаты и подключения Telegram](docs/engineering/orders-usage.md).

Касса: `/staff/pos`, demo-оплата и общий готовый остаток с online. [Инструкция](docs/engineering/pos-usage.md).

Отчёты: `/staff/reports`, право reporting.read. [Инструкция](docs/engineering/reporting-usage.md).

Финансы и зарплата: `/staff/finance`, право finance.manage. [Инструкция](docs/engineering/finance-usage.md).
Локальный стенд наполняется [демонстрационными товарами](docs/engineering/demo-data.md): `python3 -I scripts/seed_demo.py`.
