# Frontend

Подтверждено: React + TypeScript, адаптивность, dark/light, русские тексты, password toggle.
Предложено: Vite, React Router, TanStack Query для server state; обычное локальное состояние
для UI, форма через React Hook Form + Zod при обоснованной необходимости.
В FOUNDATION-01 выбраны React 19, TypeScript 5.9, Vite 8; версии закреплены pnpm-lock.yaml.
Router, Query и библиотеки форм пока не подключены: главная, `/staff`, `/staff/inventory`, `/staff/production` и `/staff/catalog` выбираются
по pathname; формы используют локальное состояние. Identity, inventory, production и catalog используют общий HTTP-клиент с CSRF/no-store,
проверяет JSON во время выполнения и получает типы из OpenAPI. Общие компоненты Input/PasswordInput/PhoneInput и CheckboxGroup содержат связанные
ошибки, placeholders и password toggle. Identity-композиции находятся в features/identity. Даты сессий выводятся в Asia/Almaty.

Общие компоненты: Button, Input, PhoneInput, PasswordInput, QuantityInput, Dialog,
Toast, ThemeToggle, ProductCard, OrderStatus. API-запросы не дублировать в каждом компоненте.
TypeScript strict; unknown для внешних данных, без подавления ошибок через произвольный any.
Цена и остаток из клиента не авторитетны. Роль определяет видимость, но backend всё равно проверяет доступ.

Темы через semantic CSS tokens (background, surface, text, border, danger, focus),
выбор light/dark/system сохраняется локально. Первый рендер учитывает выбор без вспышки темы.
Проверить формы, модалки, toast, disabled/loading и графики в обеих темах.

Предложенная матрица ширин: 360, 390, 768, 1280, 1440 px. Меню — mobile-first;
таблицы управления преобразуются в карточки или имеют обозначенную локальную прокрутку.
У страницы нет горизонтального overflow, основные действия доступны пальцем и клавиатурой.
Состояние не передаётся одним цветом; заметный focus; подписи полей и ошибки связаны программно.
Цель доступности WCAG 2.2 AA требует проверки, а не заявления по одному скриншоту.

Источник: [React input](https://react.dev/reference/react-dom/components/input).

UI-01: [каталог реализованных компонентов](ui-components.md). Темой управляет icon button
с native dialog. Общий PageShell используется на обоих экранах.

CATALOG-01: главная показывает публичное меню; управление находится в features/catalog.
Staff-страницы загружаются через React.lazy/Suspense, гостю не загружаются формы сотрудников.
[Порядок работы с меню](catalog-usage.md).

ORDERS-01 добавляет `/orders` и `/staff/orders`, общие типизированные orders API, корзину,
временные оформления, списки после оплаты и форму слота. Polling 15 секунд; checkout и mock-payment
используют useOperation для сохранения ключа повтора. Гостевой credential недоступен JavaScript.
Focus полей — внутренний контур 2px в цвете темы, клавиатурная видимость сохранена.

POS-01: `/staff/pos`, отдельная корзина и история demo-кассы. Неизвестный результат
сохраняется как key/payload в sessionStorage конкретного сотрудника, без auth secrets.
Повтор после reload использует тот же ключ; новая продажа блокируется до результата.

## Стили и крупные компоненты (24.10.2026)

`src/app/styles.css` только подключает части из `src/app/styles/` (01-base … 09-operations)
в порядке каскада: более поздний файл переопределяет ранний, менять порядок нельзя.
Новые стили добавлять в файл своего раздела. Экран сотрудников разделён на `CreateStaff`,
`FindStaff`, `StaffDialog`, `StaffAccess` (роли и пароль), `StaffManagement`; зарплата — на
`PayrollView`, `WorkerDialog`, `PayDialog`, `TimesheetView`, `MoneyList`. Компонентный файл
экспортирует только компоненты, константы — в отдельных модулях (правило react-refresh).
