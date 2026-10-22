"""Fill a local AsHana stand with demo goods through the public HTTP API.

Every write goes through the same use cases, audit and idempotency as the UI.
The password is read from a local ignored file and never printed.
"""

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

ASTANA = timezone(timedelta(hours=5))

RAW = [
    # name, unit, quantity, purchase price per unit (tiyn)
    ("Куриное филе", "kg", "20", 220000),
    ("Говядина", "kg", "15", 380000),
    ("Гречка", "kg", "15", 70000),
    ("Рис", "kg", "15", 65000),
    ("Картофель", "kg", "30", 25000),
    ("Морковь", "kg", "10", 20000),
    ("Лук репчатый", "kg", "10", 18000),
    ("Огурцы", "kg", "8", 90000),
    ("Помидоры", "kg", "8", 110000),
    ("Мука", "kg", "15", 30000),
    ("Масло подсолнечное", "l", "10", 90000),
    ("Молоко", "l", "10", 45000),
]
PURCHASED = [
    # name, category, quantity, purchase, sale, barcode
    ("Круассан с шоколадом", "Выпечка", "30", 25000, 45000, "4870000000017"),
    ("Вода без газа 0,5 л", "Напитки", "50", 12000, 25000, "4870000000024"),
    ("Яблочный сок 0,33 л", "Напитки", "40", 25000, 45000, "4870000000031"),
    ("Чай чёрный", "Напитки", "60", 5000, 20000, "4870000000048"),
    ("Йогурт натуральный", "Десерты", "30", 28000, 50000, "4870000000055"),
    ("Приборы: вилка, ложка, салфетка", "Приборы", "200", 3000, 10000, None),
    ("Контейнер с крышкой", "Приборы", "200", 6000, 15000, None),
]
PREPARED = [
    # name, category, unit, sale, portion, yield, description, ingredients per batch
    (
        "Куриное филе с гречкой",
        "Комплексы",
        "portion",
        120000,
        "350 г",
        20,
        "Куриное филе, гречка, овощи, соус.",
        [("Куриное филе", "3", "kg"), ("Гречка", "2", "kg"), ("Морковь", "0.5", "kg")],
    ),
    (
        "Плов с говядиной",
        "Комплексы",
        "portion",
        160000,
        "350 г",
        20,
        "Рис, говядина, морковь, лук.",
        [
            ("Рис", "2.5", "kg"),
            ("Говядина", "2.5", "kg"),
            ("Морковь", "1.5", "kg"),
            ("Лук репчатый", "0.5", "kg"),
            ("Масло подсолнечное", "0.5", "l"),
        ],
    ),
    (
        "Курица с картофелем",
        "Комплексы",
        "portion",
        150000,
        "350 г",
        20,
        "Запечённое куриное филе и картофель.",
        [("Куриное филе", "3", "kg"), ("Картофель", "4", "kg")],
    ),
    (
        "Куриный суп",
        "Супы",
        "portion",
        90000,
        "300 мл",
        25,
        "Куриный бульон, картофель, морковь.",
        [("Куриное филе", "1.5", "kg"), ("Картофель", "2", "kg"), ("Морковь", "0.5", "kg")],
    ),
    (
        "Овощной салат",
        "Салаты",
        "portion",
        60000,
        "200 г",
        20,
        "Огурцы, помидоры, масло.",
        [("Огурцы", "2", "kg"), ("Помидоры", "2", "kg"), ("Масло подсолнечное", "0.2", "l")],
    ),
    (
        "Картофельное пюре",
        "Гарниры",
        "portion",
        50000,
        "250 г",
        20,
        "Картофель, молоко.",
        [("Картофель", "5", "kg"), ("Молоко", "1", "l")],
    ),
    (
        "Самса с мясом",
        "Выпечка",
        "pcs",
        50000,
        "1 шт.",
        30,
        "Слоёное тесто, говядина, лук.",
        [("Мука", "3", "kg"), ("Говядина", "2", "kg"), ("Лук репчатый", "1", "kg")],
    ),
]


class Api:
    def __init__(self, base: str, origin: str) -> None:
        self.base, self.origin = base.rstrip("/"), origin
        self.http = build_opener(HTTPCookieProcessor(CookieJar()))
        self.csrf = ""

    def call(self, method: str, path: str, body: object = None, *, key: bool = False) -> object:
        headers = {"Content-Type": "application/json", "Origin": self.origin}
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        if key:
            headers["Idempotency-Key"] = str(uuid.uuid4())
        data = None if body is None else json.dumps(body).encode()
        request = Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.http.open(request, timeout=30) as response:
                raw = response.read()
        except HTTPError as error:
            detail = error.read().decode(errors="replace")[:500]
            raise SystemExit(f"{method} {path}: {error.code} {detail}") from None
        return json.loads(raw) if raw else None

    def login(self, login: str, password: str) -> None:
        self.csrf = self.call("GET", "/auth/csrf")["csrf_token"]  # type: ignore[index]
        self.call("POST", "/auth/login", {"login": login, "password": password})
        self.csrf = self.call("GET", "/auth/csrf")["csrf_token"]  # type: ignore[index]


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--origin", default="http://127.0.0.1:8080")
    parser.add_argument("--credentials", default="secret/admin.json")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    credentials = json.loads(Path(args.credentials).read_text())
    api = Api(args.api, args.origin)
    api.login(credentials["login"], credentials["password"])

    existing = api.call("GET", "/inventory/items?limit=100")
    now = datetime.now(ASTANA)
    periods = api.call("GET", f"/catalog/periods?day={now:%Y-%m-%d}")
    if any(p["name"] == "Меню столовой" for p in periods):  # type: ignore[union-attr]
        sys.exit("Демо-данные уже созданы; повторное наполнение не выполняется.")

    supplier_name = "ТОО «Продукты Астана»"
    known = api.call("GET", "/inventory/directories?kind=supplier")
    supplier_id = next((d["id"] for d in known if d["name"] == supplier_name), None)  # type: ignore[union-attr]
    if supplier_id is None:
        supplier_id = api.call(
            "POST", "/inventory/directories", {"kind": "supplier", "name": supplier_name}, key=True
        )["subject_id"]  # type: ignore[index]
    warehouse_id = "00000000-0000-0000-0000-000000000001"
    cash_id = "00000000-0000-0000-0000-000000000002"

    item_ids: dict[str, str] = {}
    # Categories are a shared directory; create each name once before using it.
    known = {d["name"] for d in api.call("GET", "/inventory/directories?kind=category")}  # type: ignore[union-attr]
    for name in sorted({"Сырьё"} | {c for _, c, *_ in PURCHASED} | {c for _, c, *_ in PREPARED}):
        if name not in known:
            api.call("POST", "/inventory/directories", {"kind": "category", "name": name}, key=True)

    for item in existing:  # type: ignore[union-attr]
        item_ids[item["name"]] = item["id"]

    def create_item(name: str, kind: str, unit: str, **extra: object) -> str:
        if name in item_ids:
            return item_ids[name]
        created = api.call(
            "POST",
            "/inventory/items",
            {"name": name, "kind": kind, "unit": unit, **extra},
            key=True,
        )
        item_ids[name] = created["subject_id"]  # type: ignore[index]
        return item_ids[name]

    for name, unit, _, price in RAW:
        create_item(name, "raw", unit, category="Сырьё", purchase_price_minor=price)
    for name, category, _, purchase, sale, barcode in PURCHASED:
        create_item(
            name,
            "purchased",
            "pcs",
            category=category,
            purchase_price_minor=purchase,
            sale_price_minor=sale,
            barcode=barcode,
            # Bought-in goods stay on sale in every period while stock lasts.
            always_on_menu=True,
        )
    for name, category, unit, sale, *_ in PREPARED:
        create_item(name, "prepared", unit, category=category, sale_price_minor=sale)

    received = now - timedelta(hours=2)
    lines = [
        {
            "item_id": item_ids[name],
            "quantity": quantity,
            "unit": unit,
            "unit_cost_minor": price,
            "expires_at": iso(now + timedelta(days=10)),
        }
        for name, unit, quantity, price in RAW
    ] + [
        {
            "item_id": item_ids[name],
            "quantity": quantity,
            "unit": "pcs",
            "unit_cost_minor": purchase,
            "expires_at": iso(now + timedelta(days=args.days + 3)),
        }
        for name, _, quantity, purchase, _, _ in PURCHASED
    ]
    invoice_number = f"НК-{now:%Y%m%d}-1"
    invoices = api.call("GET", "/inventory/invoices")
    if not any(i["number"] == invoice_number for i in invoices):  # type: ignore[union-attr]
        api.call(
            "POST",
            "/inventory/invoices",
            {
                "number": invoice_number,
                "supplier_id": supplier_id,
                "warehouse_id": warehouse_id,
                "payment_method_id": cash_id,
                "received_at": iso(received),
                "expenses_minor": 500000,
                "note": "Начальное наполнение",
                "lines": lines,
            },
            key=True,
        )

    batch_by_item: dict[str, str] = {}
    for name, *_ in RAW:
        batches = api.call("GET", f"/production/raw-batches?item_id={item_ids[name]}")
        batch_by_item[item_ids[name]] = batches[0]["id"]  # type: ignore[index]

    recipes = {r["output_item_id"] for r in api.call("GET", "/production/recipes?limit=100")}  # type: ignore[union-attr]
    for name, _, _, _, portion, yield_, _, ingredients in PREPARED:
        if item_ids[name] in recipes:
            continue
        amount, measure = portion.split()[0], portion.split()[1]
        portion_quantity, portion_unit = (
            (amount, "ml") if measure == "мл" else (amount, "g") if measure == "г" else ("120", "g")
        )
        recipe = api.call(
            "POST",
            "/production/recipes",
            {
                "output_item_id": item_ids[name],
                "previous_version": 0,
                "expected_yield": yield_,
                "portion_quantity": portion_quantity,
                "portion_unit": portion_unit,
                "instructions": f"Порция {portion}. Демонстрационный рецепт.",
                "lines": [
                    {"item_id": item_ids[i], "quantity": q, "unit": u} for i, q, u in ingredients
                ],
            },
            key=True,
        )
        api.call(
            "POST",
            "/production/batches",
            {
                "recipe_id": recipe["subject_id"],  # type: ignore[index]
                "label": f"{name} — выпуск {now:%d.%m}",
                "actual_yield": yield_,
                "expires_at": iso(now + timedelta(days=args.days + 1)),
                "suitability_confirmed": True,
                "consumption": [
                    {"batch_id": batch_by_item[item_ids[i]], "quantity": q, "unit": u}
                    for i, q, u in ingredients
                ],
            },
            key=True,
        )

    # Purchased goods join every new period automatically (always_on_menu).
    menu = [(n, c, s, p, d) for n, c, _, s, p, _, d, _ in PREPARED]
    slots = 0
    for day in range(args.days):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=day)
        period = api.call(
            "POST",
            "/catalog/periods",
            {
                "name": "Меню столовой",
                "starts_at": iso(start + timedelta(hours=7)),
                "ends_at": iso(start + timedelta(hours=23, minutes=59)),
                "published": True,
                "expected_version": 0,
            },
            key=True,
        )
        period_id = period["subject_id"]  # type: ignore[index]
        for name, category, price, portion, description in menu:
            api.call(
                "POST",
                f"/catalog/periods/{period_id}/entries",
                {
                    "item_id": item_ids[name],
                    "description": description,
                    "category": category,
                    "portion_label": portion,
                    "price_minor": price,
                    "published": True,
                    "expected_version": 0,
                },
                key=True,
            )
        for minute in range(8 * 60, 23 * 60 + 40, 10):
            starts = start + timedelta(minutes=minute)
            if starts - timedelta(minutes=25) <= now:
                continue
            api.call(
                "POST",
                "/orders/staff/slots",
                {
                    "period_id": period_id,
                    "starts_at": iso(starts),
                    "ends_at": iso(starts + timedelta(minutes=10)),
                    "cutoff_at": iso(starts - timedelta(minutes=15)),
                    "capacity": 10,
                    "enabled": True,
                    "expected_version": 0,
                },
                key=True,
            )
            slots += 1
    print(
        f"Готово: {len(item_ids)} товаров, {len(PREPARED)} выпусков, "
        f"{len(menu)} позиций меню на {args.days} дн., {slots} слотов."
    )


if __name__ == "__main__":
    main()
