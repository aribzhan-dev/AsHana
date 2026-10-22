import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import TracebackType
from typing import Protocol
from uuid import UUID, uuid4

from ashana.modules.finance.domain.models import (
    ALMATY,
    Accrual,
    Money,
    Owner,
    Plan,
    ProfitAndLoss,
    Shift,
    Worker,
    hourly_pay,
    month_bounds,
    share,
)
from ashana.modules.finance.infrastructure.database import PostgresFinanceRepository
from ashana.modules.inventory.application.ports import InventoryRepository
from ashana.modules.inventory.domain.models import InventoryError, Result, invalid, text_value


class FinanceUnitOfWork(Protocol):
    repository: PostgresFinanceRepository
    stock: InventoryRepository

    def __enter__(self) -> "FinanceUnitOfWork": ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    def authorize(self, token: str, permission: str | None = "finance.manage") -> UUID: ...
    def commit(self) -> None: ...


def amount(value: int, field: str, *, allow_negative: bool = False) -> int:
    low = -999999999999 if allow_negative else 1
    if type(value) is not int or not low <= value <= 999999999999 or value == 0:
        raise invalid(field, "Укажите сумму")
    return value


class FinanceService:
    def __init__(
        self,
        uow: Callable[[], FinanceUnitOfWork],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.uow, self.clock = uow, clock

    def _write(
        self,
        token: str,
        operation: str,
        key: UUID,
        payload: dict[str, object],
        action: Callable[[FinanceUnitOfWork, UUID, datetime], Result],
        permission: str | None = "finance.manage",
    ) -> Result:
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode()
        ).hexdigest()
        with self.uow() as uow:
            actor = uow.authorize(token, permission)
            replay = uow.stock.replay(actor, operation, key, fingerprint)
            if replay:
                return replay
            now = self.clock()
            result = action(uow, actor, now)
            uow.stock.audit(actor, operation, result.subject_id, now)
            uow.stock.remember(actor, operation, key, fingerprint, result, now)
            uow.commit()
            return result

    def _method(self, uow: FinanceUnitOfWork, method_id: UUID) -> None:
        if not uow.repository.directory_name(method_id, "payment_method"):
            raise invalid("payment_method_id", "Выберите способ оплаты из настроек")

    def _moment(self, at: datetime, now: datetime, field: str) -> datetime:
        if not at.tzinfo or at > now + timedelta(minutes=5):
            raise invalid(field, "Дата не может быть в будущем")
        return at

    # --- reports -------------------------------------------------------------------------
    def _accruals(
        self, repo: PostgresFinanceRepository, month: date, pnl: ProfitAndLoss
    ) -> list[Accrual]:
        """Fixed, daily, hourly and sales pay first; profit shares use the profit after them."""
        workers = repo.workers()
        shifts = repo.shifts(month)
        payments = repo.salary_payments(month)
        all_sales = pnl.net_revenue
        partial: list[tuple[Worker, int, Decimal, int, int, int, int, int]] = []
        for w in workers:
            mine = [s for s in shifts if s.worker_id == w.id and not s.voided and s.ends_at]
            days = len({s.starts_at.astimezone(ALMATY).date() for s in mine})
            worked = sum((s.hours for s in mine), Decimal(0))
            sales_base = (
                repo.personal_sales(w.user_id, month)
                if w.sales_base == "personal" and w.user_id
                else all_sales
            )
            monthly = w.monthly_minor if w.active or days else 0
            partial.append(
                (
                    w,
                    days,
                    worked,
                    monthly,
                    days * w.daily_minor,
                    hourly_pay(worked, w.hourly_minor),
                    sales_base,
                    share(sales_base, w.sales_bp),
                )
            )
        pnl.payroll = sum(p[3] + p[4] + p[5] + p[7] for p in partial)
        result = []
        for w, days, worked, monthly, daily, hourly, sales_base, sales in partial:
            base = pnl.base(w.profit_base)
            profit = share(base, w.profit_bp)
            paid = sum(p.amount_minor for p in payments if p.subject_id == w.id)
            result.append(
                Accrual(
                    w, days, worked, monthly, daily, hourly, sales_base, sales, base, profit, paid
                )
            )
        pnl.profit_shares = sum(a.profit for a in result)
        return result

    def month(self, token: str, month: date) -> tuple[ProfitAndLoss, list[Accrual]]:
        month_bounds(month)
        with self.uow() as uow:
            uow.authorize(token)
            pnl = uow.repository.profit_and_loss(month)
            pnl.commission = sum(
                share(int(str(m["amount"])), int(str(m["commission_bp"])))
                for m in pnl.sales_by_method
            )
            accruals = self._accruals(uow.repository, month, pnl)
            return pnl, accruals

    def details(self, token: str, month: date) -> dict[str, object]:
        """Lists behind the monthly figures, for the finance screen."""
        month_bounds(month)
        with self.uow() as uow:
            uow.authorize(token)
            r = uow.repository
            return {
                "expenses": r.expenses(month),
                "payments": r.salary_payments(month),
                "dividends": r.dividends(month),
                "shifts": r.shifts(month),
                "owners": r.owners(),
                "plans": r.plans(month),
                "categories": r.category_sales(month),
                "daily": r.daily_sales(month),
                "staff": r.staff(),
            }

    # --- settings: commission, expenses, plans, owners -------------------------------------
    def set_commission(self, token: str, key: UUID, method_id: UUID, basis_points: int) -> Result:
        if type(basis_points) is not int or not 0 <= basis_points <= 10000:
            raise invalid("commission_bp", "Комиссия от 0 до 100%")

        def action(uow: FinanceUnitOfWork, actor: UUID, now: datetime) -> Result:
            if not uow.repository.set_commission(method_id, basis_points):
                raise InventoryError("NOT_FOUND", "Способ оплаты не найден")
            return Result(method_id, 1)

        return self._write(
            token, "commission_set", key, {"m": method_id, "bp": basis_points}, action
        )

    def add_expense(
        self,
        token: str,
        key: UUID,
        category_id: UUID,
        amount_minor: int,
        method_id: UUID,
        spent_at: datetime,
        note: str,
    ) -> Result:
        def action(uow: FinanceUnitOfWork, actor: UUID, now: datetime) -> Result:
            if not uow.repository.directory_name(category_id, "expense_category"):
                raise invalid("category_id", "Выберите статью расходов")
            self._method(uow, method_id)
            expense = Money(
                uuid4(),
                category_id,
                amount(amount_minor, "amount_minor", allow_negative=True),
                method_id,
                self._moment(spent_at, now, "spent_at"),
                text_value(note, "note", 200) if note.strip() else "",
                actor,
                now,
            )
            uow.repository.add_expense(expense)
            return Result(expense.id, 1)

        return self._write(
            token,
            "expense_added",
            key,
            {"c": category_id, "a": amount_minor, "m": method_id, "t": spent_at, "n": note},
            action,
        )

    def save_plan(
        self, token: str, key: UUID, month: date, category: str, target_minor: int, version: int
    ) -> Result:
        month_bounds(month)
        if type(target_minor) is not int or not 0 <= target_minor <= 999999999999:
            raise invalid("target_minor", "Укажите план от 0 ₸")
        category = text_value(category, "category", 60) if category.strip() else ""

        def action(uow: FinanceUnitOfWork, actor: UUID, now: datetime) -> Result:
            uow.repository.lock(f"plan:{month}:{category}")
            current = next((p for p in uow.repository.plans(month) if p.category == category), None)
            if (current.version if current else 0) != version:
                raise InventoryError("STALE_PLAN", "План изменился. Обновите страницу")
            plan = Plan(month, category, target_minor, version + 1)
            uow.repository.save_plan(plan, actor, now)
            return Result(actor, plan.version)

        return self._write(
            token,
            "plan_saved",
            key,
            {"m": month, "c": category, "t": target_minor, "v": version},
            action,
        )

    def save_owner(
        self,
        token: str,
        key: UUID,
        owner_id: UUID | None,
        name: str,
        share_bp: int,
        active: bool,
        version: int,
    ) -> Result:
        if type(share_bp) is not int or not 1 <= share_bp <= 10000:
            raise invalid("share_bp", "Доля от 0,01 до 100%")

        def action(uow: FinanceUnitOfWork, actor: UUID, now: datetime) -> Result:
            uow.repository.lock("owners")
            owners = uow.repository.owners()
            current = next((o for o in owners if o.id == owner_id), None) if owner_id else None
            if owner_id and not current:
                raise InventoryError("NOT_FOUND", "Учредитель не найден")
            if (current.version if current else 0) != version:
                raise InventoryError("STALE_OWNER", "Данные изменились. Обновите страницу")
            others = sum(o.share_bp for o in owners if o.active and o.id != owner_id)
            if active and others + share_bp > 10000:
                raise invalid("share_bp", "Сумма долей учредителей больше 100%")
            owner = Owner(
                owner_id or uuid4(),
                text_value(name, "name", 100),
                share_bp,
                active,
                version + 1,
                current.created_at if current else now,
            )
            uow.repository.save_owner(owner, new=current is None)
            return Result(owner.id, owner.version)

        return self._write(
            token,
            "owner_saved",
            key,
            {"o": owner_id, "n": name, "s": share_bp, "a": active, "v": version},
            action,
        )

    def pay_dividend(
        self,
        token: str,
        key: UUID,
        owner_id: UUID,
        month: date,
        amount_minor: int,
        method_id: UUID,
        paid_at: datetime,
        note: str,
    ) -> Result:
        month_bounds(month)

        def action(uow: FinanceUnitOfWork, actor: UUID, now: datetime) -> Result:
            if not any(o.id == owner_id for o in uow.repository.owners()):
                raise InventoryError("NOT_FOUND", "Учредитель не найден")
            self._method(uow, method_id)
            payment = Money(
                uuid4(),
                owner_id,
                amount(amount_minor, "amount_minor"),
                method_id,
                self._moment(paid_at, now, "paid_at"),
                text_value(note, "note", 200) if note.strip() else "",
                actor,
                now,
                month,
            )
            uow.repository.add_dividend(payment)
            return Result(payment.id, 1)

        return self._write(
            token,
            "dividend_paid",
            key,
            {"o": owner_id, "m": month, "a": amount_minor, "p": method_id, "t": paid_at},
            action,
        )

    # --- payroll -------------------------------------------------------------------------
    def save_worker(
        self,
        token: str,
        key: UUID,
        worker_id: UUID | None,
        version: int,
        name: str,
        position: str,
        user_id: UUID | None,
        active: bool,
        monthly_minor: int,
        daily_minor: int,
        hourly_minor: int,
        sales_bp: int,
        sales_base: str,
        profit_bp: int,
        profit_base: str,
    ) -> Result:
        def action(uow: FinanceUnitOfWork, actor: UUID, now: datetime) -> Result:
            current = uow.repository.worker(worker_id, lock=True) if worker_id else None
            if worker_id and not current:
                raise InventoryError("NOT_FOUND", "Сотрудник не найден")
            if (current.version if current else 0) != version:
                raise InventoryError("STALE_WORKER", "Данные изменились. Обновите страницу")
            if user_id and not any(s["id"] == str(user_id) for s in uow.repository.staff()):
                raise invalid("user_id", "Аккаунт не найден")
            worker = Worker(
                worker_id or uuid4(),
                text_value(name, "name", 100),
                text_value(position, "position", 100) if position.strip() else "",
                user_id,
                active,
                monthly_minor,
                daily_minor,
                hourly_minor,
                sales_bp,
                sales_base,
                profit_bp,
                profit_base,
                version + 1,
                current.created_at if current else now,
                now,
            )
            worker.validate()
            uow.repository.save_worker(worker, new=current is None)
            return Result(worker.id, worker.version)

        return self._write(
            token,
            "worker_saved",
            key,
            {
                "w": worker_id,
                "v": version,
                "n": name,
                "p": position,
                "u": user_id,
                "a": active,
                "pay": [monthly_minor, daily_minor, hourly_minor],
                "s": [sales_bp, sales_base],
                "r": [profit_bp, profit_base],
            },
            action,
        )

    def my_shift(self, token: str) -> tuple[Worker | None, Shift | None]:
        with self.uow() as uow:
            user = uow.authorize(token, None)
            worker = uow.repository.worker_for_user(user)
            return worker, uow.repository.open_shift(worker.id) if worker else None

    def toggle_shift(self, token: str, key: UUID, start: bool) -> Result:
        """Staff check in/out themselves; the account must be linked to a payroll worker."""

        def action(uow: FinanceUnitOfWork, actor: UUID, now: datetime) -> Result:
            worker = uow.repository.worker_for_user(actor)
            if not worker:
                raise InventoryError("NO_WORKER", "Аккаунт не привязан к сотруднику в зарплате")
            current = uow.repository.open_shift(worker.id)
            if start:
                if current:
                    raise InventoryError("SHIFT_OPEN", "Смена уже начата")
                shift = Shift(uuid4(), worker.id, now, None, "self", "", False, actor, now, now)
                uow.repository.add_shift(shift)
                return Result(shift.id, 1)
            if not current:
                raise InventoryError("NO_SHIFT", "Смена не начата")
            # Forgotten check-outs are capped at 16 hours; a manager can correct them.
            end = min(now, current.starts_at + timedelta(hours=16))
            closed = replace(current, ends_at=end, updated_at=now)
            uow.repository.update_shift(closed)
            return Result(current.id, 2)

        return self._write(token, "shift_toggled", key, {"start": start}, action, None)

    def add_shift(
        self,
        token: str,
        key: UUID,
        worker_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        note: str,
    ) -> Result:
        def action(uow: FinanceUnitOfWork, actor: UUID, now: datetime) -> Result:
            if not uow.repository.worker(worker_id):
                raise InventoryError("NOT_FOUND", "Сотрудник не найден")
            if not starts_at.tzinfo or not ends_at.tzinfo or ends_at <= starts_at:
                raise invalid("ends_at", "Окончание должно быть позже начала")
            if ends_at - starts_at > timedelta(hours=24) or ends_at > now + timedelta(minutes=5):
                raise invalid("ends_at", "Смена до 24 часов и не в будущем")
            shift = Shift(
                uuid4(),
                worker_id,
                starts_at,
                ends_at,
                "manager",
                text_value(note, "note", 200) if note.strip() else "",
                False,
                actor,
                now,
                now,
            )
            uow.repository.add_shift(shift)
            return Result(shift.id, 1)

        return self._write(
            token,
            "shift_added",
            key,
            {"w": worker_id, "s": starts_at, "e": ends_at, "n": note},
            action,
        )

    def void_shift(self, token: str, key: UUID, shift_id: UUID, note: str) -> Result:
        def action(uow: FinanceUnitOfWork, actor: UUID, now: datetime) -> Result:
            shift = uow.repository.shift(shift_id)
            if not shift:
                raise InventoryError("NOT_FOUND", "Смена не найдена")
            if shift.voided:
                return Result(shift.id, 2)
            uow.repository.update_shift(
                replace(shift, voided=True, note=text_value(note, "note", 200), updated_at=now)
            )
            return Result(shift.id, 2)

        return self._write(token, "shift_voided", key, {"s": shift_id, "n": note}, action)

    def pay_salary(
        self,
        token: str,
        key: UUID,
        worker_id: UUID,
        month: date,
        kind: str,
        amount_minor: int,
        method_id: UUID,
        paid_at: datetime,
        note: str,
    ) -> Result:
        month_bounds(month)
        if kind not in ("advance", "salary", "bonus"):
            raise invalid("kind", "Выберите вид выплаты")

        def action(uow: FinanceUnitOfWork, actor: UUID, now: datetime) -> Result:
            uow.repository.lock(f"payroll:{worker_id}:{month}")
            if not uow.repository.worker(worker_id):
                raise InventoryError("NOT_FOUND", "Сотрудник не найден")
            self._method(uow, method_id)
            payment = Money(
                uuid4(),
                worker_id,
                amount(amount_minor, "amount_minor"),
                method_id,
                self._moment(paid_at, now, "paid_at"),
                text_value(note, "note", 200) if note.strip() else "",
                actor,
                now,
                month,
                kind,
            )
            uow.repository.add_salary_payment(payment)
            return Result(payment.id, 1)

        return self._write(
            token,
            "salary_paid",
            key,
            {
                "w": worker_id,
                "m": month,
                "k": kind,
                "a": amount_minor,
                "p": method_id,
                "t": paid_at,
                "n": note,
            },
            action,
        )
