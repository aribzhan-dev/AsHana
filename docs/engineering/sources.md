# Проверенные публичные источники

Проверено при подготовке 20.10.2026. Эти ссылки объясняют возможности технологий;
они не доказывают, что AsHana уже реализует их корректно.

- [FastAPI dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) — связывание адаптеров в composition root; проверено через Context7.
- [React input](https://react.dev/reference/react-dom/components/input) — управляемые поля; проверено через Context7.
- [React TypeScript](https://react.dev/learn/typescript) — типизация интерфейса.
- [PostgreSQL locking](https://www.postgresql.org/docs/current/explicit-locking.html) — конкурентная запись и блокировки; источник предыдущего обсуждения.
- [Docker Compose readiness](https://docs.docker.com/compose/how-tos/startup-order/) — healthcheck и порядок запуска.
- [ITU Kazakhstan](https://www.itu.int/oth/T020200006F) — актуальная страница плана нумерации.
- [ITU international number length](https://www.itu.int/dms_pub/itu-t/oth/02/02/T020200006F0002PDFE.pdf) — 11 цифр международного номера.

Перед фиксацией версий проверить актуальные совместимые релизы; не использовать тег latest
как воспроизводимую спецификацию. Перечень источников не разрешает публикацию файлов проекта.

## IDENTITY-01, 20.10.2026

Для реализации проверены официальные примеры через Context7:
[argon2-cffi](https://argon2-cffi.readthedocs.io/en/stable/howto.html) — PasswordHasher, verify, check_needs_rehash;
[python-phonenumbers](https://github.com/daviddrysdale/python-phonenumbers) — валидность, регион и тип номера.
В lockfiles: argon2-cffi 25.1.0, phonenumbers 9.0.41, libphonenumber-js 1.13.15.

## UI-01, 20.10.2026

[MDN dialog](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog) —
showModal, модальность, Escape и управление фокусом; проверено при реализации общих диалогов.

ORDERS-01: [Telegram Bot API — sendMessage](https://core.telegram.org/bots/api#sendmessage)
проверен при реализации 21.10.2026. Используется фиксированный HTTPS endpoint, обычный текст,
chat_id и protect_content; внешняя отправка в этой сессии не выполнялась.
