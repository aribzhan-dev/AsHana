# Архитектурные решения

Статус в каждом ADR обязателен; предложенное не считать одобренным владельцем.

- [ADR-0001: Стек и Clean Architecture](0001-stack-and-clean-architecture.md) — Стек и принцип подтверждены; модульная структура предложена.
- [ADR-0002: Готовые партии и атомарные резервы](0002-stock-reservations.md) — Предложено; реализовано в ORDERS-01/POS-01.
- [ADR-0003: Изолированная mock-оплата](0003-mock-payments.md) — Mock подтверждён; протокол предложен.
- [ADR-0004: Серверные cookie-сессии](0004-session-auth.md) — Предложено.
- [ADR-0005: Надёжные уведомления и online-only](0005-outbox-and-online-only.md) — Предложено; реализовано: outbox (ORDERS-01), WebSocket (ADR-0020).
- [ADR-0006: Локальная основа приложения](0006-local-foundation.md) — Выбрано при реализации FOUNDATION-01.

- [ADR-0007: аккаунты только для сотрудников](0007-staff-only-identity.md)

- [ADR-0008: логин сотрудника и общие UI-компоненты](0008-staff-login-and-ui.md)

- [ADR-0009 — склад и журнал движений](0009-inventory-ledger.md) — техническое решение INVENTORY-01.

- [ADR-0010 — версии рецептов и атомарный выпуск](0010-production-transactions.md) — техническое решение PRODUCTION-01.

- [ADR-0011 — публикация меню по готовому остатку](0011-catalog-publication.md) — техническое решение CATALOG-01.

- [ADR-0012 — оформление до оплаты, заказ после оплаты](0012-checkout-before-order.md) — реализовано ORDERS-01; уточняет ADR-0002/0003/0005.

- [ADR-0013 — комплектация готовой еды и однократная выдача](0013-serving-ready-food.md).

- [ADR-0014 — demo-касса и общий остаток](0014-demo-counter-sales.md).

- [ADR-0015 — read-only отчёты](0015-read-only-reports.md).

- [0016: рабочий кабинет и каталог ролей](0016-workspace-role-catalog.md)
- [0017 — Накладная прихода и рабочие списания](0017-receiving-workspace.md)
- [0018 — получение заказа по QR-коду](0018-qr-pickup.md)
- [0019 — категории, постоянные товары, «с собой», возвраты, долги, отчёты](0019-operations-v2.md)
- [0020 — живые экраны кухни и кассы через WebSocket](0020-live-staff-screens.md)
- [0021 — финансы месяца и зарплата](0021-finance-and-payroll.md)
- [0022 — живая страница гостя и фото блюд](0022-guest-live-and-photos.md)
- [0023 — без возврата за заказы с сайта, «Не забрали», сброс пароля](0023-no-refunds-no-show-password-reset.md)
