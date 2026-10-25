import os
from datetime import timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from test_orders_postgres import System
from test_orders_postgres import order_system as _order_system

from ashana.bootstrap.finance import finance_service
from ashana.bootstrap.pos import pos_service
from ashana.bootstrap.settings import Settings
from ashana.modules.finance.application.service import FinanceService
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError, Role
from ashana.modules.orders.domain.models import Choice
from ashana.modules.pos.application.service import PosService
from ashana.shared.domain import BusinessError

finance_system = _order_system
pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)
Identity = tuple[Settings, IdentityService, str]
CASH = UUID("00000000-0000-0000-0000-000000000002")
CARD = UUID("00000000-0000-0000-0000-000000000003")
RENT = UUID("00000000-0000-0000-0000-000000000011")


@pytest.fixture(scope="module")
def finance(finance_system: System, system: Identity) -> FinanceService:
    return finance_service(finance_system.engine, system[1])


@pytest.fixture(scope="module")
def pos(finance_system: System, system: Identity) -> PosService:
    return pos_service(finance_system.engine, system[1], finance_system.service)


def this_month(s: System):  # type: ignore[no-untyped-def]
    return s.now.astimezone(ZoneInfo("Asia/Almaty")).date().replace(day=1)


def cashier(s: System, system: Identity) -> tuple[UUID, str]:
    _, identity, password = system
    user = identity.create_staff(
        s.token, "Кассир", f"pay.{uuid4().hex[:8]}", password, frozenset({Role.CASHIER})
    )
    return user.id, identity.login(user.login, password, "finance")[1]


def test_profit_and_loss_moves_with_sale_cost_return_expense_and_commission(
    finance_system: System, finance: FinanceService, pos: PosService
) -> None:
    s = finance_system
    month = this_month(s)
    finance.set_commission(s.token, uuid4(), CARD, 150)
    before, _ = finance.month(s.token, month)
    # setup(): 10 pcs received for a total cost of 100 tiyn -> 10 tiyn per piece.
    entry, _, _ = s.setup("10")
    sale = pos.sell(s.token, uuid4(), [Choice(entry, 4, 12345)], "success", CARD)
    pos.return_sale(s.token, uuid4(), sale.id, {entry: 1}, "Возврат", "restock")
    finance.add_expense(s.token, uuid4(), RENT, 500000, CASH, s.now, "Аренда")
    finance.add_expense(s.token, uuid4(), RENT, -100000, CASH, s.now, "Исправление")
    after, _ = finance.month(s.token, month)
    assert after.revenue - before.revenue == 4 * 12345
    assert after.returns - before.returns == 12345
    assert after.cost_of_goods - before.cost_of_goods == 30
    assert after.expenses["Аренда"] - before.expenses.get("Аренда", 0) == 400000
    assert after.commission - before.commission in (740, 741)
    assert after.simple_profit == after.gross_profit - after.operating_expenses
    assert after.full_profit == after.simple_profit - after.commission - after.payroll
    with pytest.raises(BusinessError):
        finance.add_expense(s.token, uuid4(), CASH, 100, CASH, s.now, "Не статья")
    with pytest.raises(BusinessError, match="будущем"):
        finance.add_expense(s.token, uuid4(), RENT, 100, CASH, s.now + timedelta(days=2), "")


def test_payroll_combines_schemes_personal_sales_shifts_and_payments(
    finance_system: System, finance: FinanceService, pos: PosService, system: Identity
) -> None:
    s = finance_system
    month = this_month(s)
    user, token = cashier(s, system)
    key = uuid4()
    worker = finance.save_worker(
        s.token, key, None, 0, "Айгерим", "Кассир", user, True,
        10000000, 300000, 100000, 1000, "personal", 0, "full",
    ).subject_id  # fmt: skip
    assert finance.save_worker(
        s.token, key, None, 0, "Айгерим", "Кассир", user, True,
        10000000, 300000, 100000, 1000, "personal", 0, "full",
    ).subject_id == worker  # fmt: skip
    with pytest.raises(BusinessError, match="привязан"):
        finance.save_worker(
            s.token, uuid4(), None, 0, "Двойник", "", user, True, 0, 0, 0, 0, "all", 0, "full"
        )
    entry, _, _ = s.setup("10")
    sale = pos.sell(token, uuid4(), [Choice(entry, 2, 12345)], "success", CASH)
    pos.return_sale(s.token, uuid4(), sale.id, {entry: 1}, "Возврат", "write_off")
    start = s.now - timedelta(hours=9)
    finance.add_shift(s.token, uuid4(), worker, start, start + timedelta(hours=7, minutes=30), "")
    with pytest.raises(BusinessError, match="24"):
        finance.add_shift(s.token, uuid4(), worker, start, start + timedelta(hours=25), "")
    wrong = finance.add_shift(
        s.token, uuid4(), worker, start - timedelta(days=1), start - timedelta(hours=20), ""
    ).subject_id
    finance.void_shift(s.token, uuid4(), wrong, "Ошибка табеля")
    finance.pay_salary(s.token, uuid4(), worker, month, "advance", 2000000, CASH, s.now, "Аванс")
    _, accruals = finance.month(s.token, month)
    a = next(a for a in accruals if a.worker.id == worker)
    assert (a.days, str(a.hours)) == (1, "7.5")
    assert (a.monthly, a.daily, a.hourly) == (10000000, 300000, 750000)
    assert a.sales_base_minor == 12345 and a.sales == 1235
    assert a.paid == 2000000 and a.balance == a.total - 2000000
    with pytest.raises(IdentityError):
        finance.month(token, month)


def test_self_shift_needs_link_one_open_shift_and_permissions(
    finance_system: System, finance: FinanceService, system: Identity
) -> None:
    s = finance_system
    user, token = cashier(s, system)
    with pytest.raises(BusinessError, match="не привязан"):
        finance.toggle_shift(token, uuid4(), True)
    finance.save_worker(
        s.token, uuid4(), None, 0, "Мойщица", "", user, True, 0, 500000, 0, 0, "all", 0, "full"
    )  # fmt: skip
    finance.toggle_shift(token, uuid4(), True)
    with pytest.raises(BusinessError, match="уже начата"):
        finance.toggle_shift(token, uuid4(), True)
    worker, shift = finance.my_shift(token)
    assert worker and shift and shift.ends_at is None
    finance.toggle_shift(token, uuid4(), False)
    assert finance.my_shift(token)[1] is None
    with pytest.raises(IdentityError):
        finance.add_shift(token, uuid4(), worker.id, s.now - timedelta(hours=2), s.now, "")


def test_profit_share_owners_dividends_and_plans(
    finance_system: System, finance: FinanceService
) -> None:
    s = finance_system
    month = this_month(s)
    worker = finance.save_worker(
        s.token, uuid4(), None, 0, "Управляющий", "", None, True, 0, 0, 0, 0, "all", 1000, "simple"
    ).subject_id  # fmt: skip
    pnl, accruals = finance.month(s.token, month)
    a = next(a for a in accruals if a.worker.id == worker)
    assert a.profit_base_minor == pnl.simple_profit
    assert a.profit == (round(pnl.simple_profit / 10) if pnl.simple_profit > 0 else 0)
    assert pnl.net_profit == pnl.full_profit - pnl.profit_shares
    owners = finance.details(s.token, month)["owners"]
    used = sum(o.share_bp for o in owners if o.active)  # type: ignore[attr-defined]
    free = 10000 - used
    if free > 0:
        owner = finance.save_owner(s.token, uuid4(), None, "Учредитель", free, True, 0).subject_id
        with pytest.raises(BusinessError, match="больше 100"):
            finance.save_owner(s.token, uuid4(), None, "Лишний", 1, True, 0)
        finance.pay_dividend(s.token, uuid4(), owner, month, 100000, CASH, s.now, "")
        paid = finance.details(s.token, month)["dividends"]
        assert any(d.subject_id == owner for d in paid)  # type: ignore[attr-defined]
    finance.save_plan(s.token, uuid4(), month, "Тест-план", 1000000, 0)
    with pytest.raises(BusinessError, match="изменился"):
        finance.save_plan(s.token, uuid4(), month, "Тест-план", 2000000, 0)
    finance.save_plan(s.token, uuid4(), month, "Тест-план", 2000000, 1)
    plans = finance.details(s.token, month)["plans"]
    assert any(p.target_minor == 2000000 for p in plans)  # type: ignore[attr-defined]


def test_browser_fixture_finance_manager(finance_system: System, system: Identity) -> None:
    """Own account for finance.spec.ts: logins per account are rate limited for the run."""
    _, identity, password = system
    user = identity.create_staff(
        finance_system.token, "Бухгалтер", "finance.manager", password, frozenset({Role.MANAGER})
    )
    assert "finance.manage" in user.effective_permissions
