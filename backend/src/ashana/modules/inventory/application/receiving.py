from dataclasses import asdict
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from ashana.modules.inventory.application.base import InventoryBase
from ashana.modules.inventory.application.ports import InventoryRepository
from ashana.modules.inventory.domain.models import (
    Batch,
    Invoice,
    InvoiceLine,
    InvoicePayment,
    Movement,
    quantity,
)
from ashana.shared.domain import BusinessError, Result, invalid, text_value


class ReceivingOperations(InventoryBase):
    """Supplier invoices and later payments of supplier debts."""

    def invoices(self, token: str, offset: int = 0, limit: int = 20) -> list[Invoice]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.invoices(offset, limit)

    def receive_invoice(
        self,
        token: str,
        key: UUID,
        number: str,
        supplier_id: UUID,
        warehouse_id: UUID,
        payment_method_id: UUID,
        received_at: datetime,
        expenses_minor: int,
        note: str,
        lines: list[InvoiceLine],
        paid_minor: int | None = None,
    ) -> Result:
        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            label = text_value(number, "number", 100)
            if not 1 <= len(lines) <= 100:
                raise invalid("lines", "Добавьте от 1 до 100 товаров")
            if not received_at.tzinfo or received_at > now:
                raise invalid("received_at", "Время прихода не может быть в будущем")
            if type(expenses_minor) is not int or not 0 <= expenses_minor <= 999999999999:
                raise invalid("expenses_minor", "Укажите неотрицательные расходы")
            names = []
            for kind, id in (
                ("supplier", supplier_id),
                ("warehouse", warehouse_id),
                ("payment_method", payment_method_id),
            ):
                entry = next((d for d in repo.directories(kind) if d.id == id), None)
                if not entry:
                    raise invalid(kind, "Выберите значение из справочника")
                names.append(entry.name)
            invoice_id = uuid4()
            snapshots: list[dict[str, object]] = []
            total = 0
            for line in lines:
                item = repo.item(line.item_id)
                if not item or item.kind == "prepared":
                    raise invalid("item_id", "Выберите сырьё или покупной товар")
                count = quantity(line.quantity, line.unit, item.unit)
                if not line.expires_at.tzinfo or line.expires_at <= received_at:
                    raise invalid("expires_at", "Срок годности должен быть позже прихода")
                if (
                    type(line.unit_cost_minor) is not int
                    or not 0 <= line.unit_cost_minor <= 999999999999
                ):
                    raise invalid("unit_cost_minor", "Укажите неотрицательную цену")
                cost = int(
                    (Decimal(line.quantity) * line.unit_cost_minor).quantize(
                        Decimal(1), rounding=ROUND_HALF_UP
                    )
                )
                if cost > 999999999999:
                    raise invalid("unit_cost_minor", "Превышена максимальная стоимость строки")
                batch = Batch(
                    uuid4(),
                    item.id,
                    label,
                    count,
                    Decimal(0),
                    "active",
                    1,
                    cost,
                    received_at,
                    line.expires_at,
                    names[0],
                    actor,
                    now,
                    item.unit,
                    warehouse_id=warehouse_id,
                )
                repo.add_batch(batch)
                repo.add_movement(
                    Movement(
                        uuid4(),
                        batch.id,
                        "receipt",
                        count,
                        Decimal(0),
                        count,
                        f"Накладная {label}",
                        actor,
                        now,
                        1,
                        "active",
                        "active",
                    )
                )
                repo.audit(actor, "receipt", batch.id, now)
                snapshots.append(
                    dict(
                        item_id=str(item.id),
                        name=item.name,
                        barcode=item.barcode,
                        batch_id=str(batch.id),
                        quantity=line.quantity,
                        unit=line.unit,
                        unit_cost_minor=line.unit_cost_minor,
                        total_cost_minor=cost,
                        expires_at=line.expires_at.isoformat(),
                    )
                )
                total += cost
            if total + expenses_minor > 999999999999:
                raise invalid("lines", "Превышена максимальная сумма накладной")
            paid = total + expenses_minor if paid_minor is None else paid_minor
            if type(paid) is not int or not 0 <= paid <= total + expenses_minor:
                raise invalid("paid_minor", "Оплачено может быть от 0 до суммы накладной")
            repo.add_invoice(
                Invoice(
                    invoice_id,
                    label,
                    supplier_id,
                    warehouse_id,
                    payment_method_id,
                    received_at,
                    total,
                    expenses_minor,
                    total + expenses_minor,
                    text_value(note, "note") if note.strip() else "",
                    actor,
                    now,
                    snapshots,
                    supplier_name=names[0],
                    warehouse_name=names[1],
                    payment_method_name=names[2],
                    paid_on_receipt_minor=paid,
                )
            )
            return Result(invoice_id, 1)

        return self._write(
            token,
            "invoice_received",
            key,
            dict(
                number=number,
                supplier_id=supplier_id,
                warehouse_id=warehouse_id,
                payment_method_id=payment_method_id,
                received_at=received_at,
                expenses_minor=expenses_minor,
                note=note,
                lines=[asdict(line) for line in lines],
                **({} if paid_minor is None else {"paid_minor": paid_minor}),
            ),
            action,
        )

    def invoice_payments(self, token: str, invoice_id: UUID) -> list[InvoicePayment]:
        with self.uow() as uow:
            uow.authorize(token)
            if not uow.repository.invoice(invoice_id):
                raise BusinessError("NOT_FOUND", "Накладная не найдена")
            return uow.repository.invoice_payments(invoice_id)

    def pay_invoice(
        self,
        token: str,
        key: UUID,
        invoice_id: UUID,
        amount_minor: int,
        payment_method_id: UUID,
        paid_at: datetime,
        note: str = "",
    ) -> Result:
        """Pay part or all of a supplier debt; payments are append-only."""

        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            invoice = repo.invoice(invoice_id, lock=True)
            if not invoice:
                raise BusinessError("NOT_FOUND", "Накладная не найдена")
            debt = invoice.total_minor - invoice.paid_minor
            if type(amount_minor) is not int or amount_minor < 1:
                raise invalid("amount_minor", "Укажите сумму оплаты больше нуля")
            if amount_minor > debt:
                raise BusinessError(
                    "PAYMENT_EXCEEDS_DEBT",
                    "Сумма больше долга по накладной",
                    {"amount_minor": ["Сумма больше долга по накладной"]},
                )
            if not paid_at.tzinfo or paid_at > now or paid_at < invoice.received_at:
                raise invalid("paid_at", "Дата оплаты — между приходом и текущим временем")
            if not any(d.id == payment_method_id for d in repo.directories("payment_method")):
                raise invalid("payment_method_id", "Выберите способ оплаты из настроек")
            payment = InvoicePayment(
                uuid4(),
                invoice_id,
                amount_minor,
                payment_method_id,
                text_value(note, "note") if note.strip() else "",
                actor,
                paid_at,
                now,
            )
            repo.add_invoice_payment(payment)
            repo.audit(actor, "invoice_payment", payment.id, now)
            return Result(payment.id, 1)

        return self._write(
            token,
            "invoice_paid",
            key,
            dict(
                invoice_id=invoice_id,
                amount_minor=amount_minor,
                payment_method_id=payment_method_id,
                paid_at=paid_at,
                note=note,
            ),
            action,
        )
