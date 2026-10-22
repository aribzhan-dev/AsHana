import { invoiceLineCost } from "../../shared/lib/invoice-money";
import { useEffect, useState } from "react";
import {
  receivingApi,
  type Directory,
  type PurchaseKind,
  type Invoice,
  type InvoiceInput,
} from "../../shared/api/receiving";
import { inventoryApi, type StockItem } from "../../shared/api/inventory";
import { useOperation } from "../../shared/lib/useOperation";
import { errorMessage } from "../../shared/lib/forms";
import {
  almatyNow,
  almatyInstant,
  costMinor,
  decimalText,
  stockMoney,
  stockDate,
} from "../../shared/lib/inventory-validation";
import { inventoryRu as t } from "../../shared/locales/inventory";
import { Button, IconButton } from "../../shared/ui/Button";
import { Input, Select } from "../../shared/ui/Input";
import { Alert, Card, LoadingState } from "../../shared/ui/Feedback";
import { Dialog } from "../../shared/ui/Dialog";
import { DetailsButton } from "../../shared/ui/DetailsButton";
import { ItemForm } from "../inventory/StockForms";
import { DirectoryForm } from "./Directories";
type Row = {
  id: string;
  item_id: string;
  quantity: string;
  unit: string;
  price: string;
  expires: string;
};
const fresh = (): Row => ({
  id: crypto.randomUUID(),
  item_id: "",
  quantity: "",
  unit: "pcs",
  price: "",
  expires: "",
});
export function ReceivingBoard({ onExpired }: { onExpired: () => void }) {
  const [editing, setEditing] = useState(false),
    [items, setItems] = useState<StockItem[]>([]),
    [invoices, setInvoices] = useState<Invoice[]>([]),
    [offset, setOffset] = useState(0),
    [attempt, setAttempt] = useState(0),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const [directories, setDirectories] = useState<
    Record<PurchaseKind, Directory[]>
  >({ supplier: [], warehouse: [], payment_method: [] });
  const [supplier, setSupplier] = useState(""),
    [warehouse, setWarehouse] = useState(
      "00000000-0000-0000-0000-000000000001",
    ),
    [method, setMethod] = useState("00000000-0000-0000-0000-000000000002");
  const [number, setNumber] = useState(""),
    [received, setReceived] = useState(almatyNow()),
    [expenses, setExpenses] = useState("0"),
    [paidNow, setPaidNow] = useState(""),
    [paying, setPaying] = useState<Invoice | null>(null),
    [note, setNote] = useState(""),
    [rows, setRows] = useState<Row[]>([fresh()]);
  const [create, setCreate] = useState<PurchaseKind | "product" | null>(null);
  const op = useOperation(onExpired);
  useEffect(() => {
    let active = true;
    async function load() {
      const all: StockItem[] = [];
      for (let i = 0; ; i += 100) {
        const page = await inventoryApi.items(i);
        all.push(...page);
        if (page.length < 100) break;
      }
      return all;
    }
    void Promise.all([
      load(),
      receivingApi.invoices(offset),
      receivingApi.directories("supplier"),
      receivingApi.directories("warehouse"),
      receivingApi.directories("payment_method"),
    ])
      .then(([i, v, s, w, p]) => {
        if (active) {
          setItems(i);
          setInvoices(v);
          setDirectories({ supplier: s, warehouse: w, payment_method: p });
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [offset, attempt]);
  const patch = (id: string, values: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...values } : r)));
  const goods = rows.reduce(
      (sum, r) => sum + (invoiceLineCost(r.quantity, r.price) ?? 0),
      0,
    ),
    extra = costMinor(expenses);
  // Empty means paid in full; a smaller amount leaves a supplier debt.
  const paid = paidNow.trim() ? costMinor(paidNow) : goods + (extra || 0);
  async function submit() {
    const time = almatyInstant(received);
    if (
      !number.trim() ||
      !supplier ||
      !warehouse ||
      !method ||
      !time ||
      extra === undefined ||
      paid === undefined ||
      paid > goods + extra ||
      rows.some(
        (r) =>
          !r.item_id ||
          !almatyInstant(r.expires) ||
          invoiceLineCost(r.quantity, r.price) === undefined ||
          !/^\d+(\.\d{1,3})?$/.test(decimalText(r.quantity)) ||
          Number(decimalText(r.quantity)) <= 0 ||
          (["pcs", "portion"].includes(r.unit) &&
            !Number.isInteger(Number(decimalText(r.quantity)))),
      )
    ) {
      op.setError(
        "Заполните товары, количество, цену и срок годности. Проверьте расходы, оплату и дату прихода.",
      );
      return;
    }
    const body: InvoiceInput = {
      number,
      supplier_id: supplier,
      warehouse_id: warehouse,
      payment_method_id: method,
      received_at: time,
      expenses_minor: extra,
      paid_minor: paid,
      note,
      lines: rows.map((r) => ({
        item_id: r.item_id,
        quantity: decimalText(r.quantity),
        unit: r.unit as "kg" | "l" | "pcs",
        unit_cost_minor: costMinor(r.price)!,
        expires_at: almatyInstant(r.expires)!,
      })),
    };
    if (await op.run(body, (key) => receivingApi.receive(body, key))) {
      setEditing(false);
      setRows([fresh()]);
      setNumber("");
      setExpenses("0");
      setPaidNow("");
      setNote("");
      setAttempt((n) => n + 1);
    }
  }
  const selected: Record<PurchaseKind, string> = {
    supplier,
    warehouse,
    payment_method: method,
  };
  const setters = {
    supplier: setSupplier,
    warehouse: setWarehouse,
    payment_method: setMethod,
  };
  const labels = {
    supplier: "Поставщик",
    warehouse: "Склад",
    payment_method: "Способ оплаты",
  };
  return (
    <div className="form-stack">
      <div className="page-heading">
        <div>
          <h1>Приход</h1>
          <p className="muted">Накладные, закупки и расходы</p>
        </div>
        {!editing && (
          <Button icon="plus" onClick={() => setEditing(true)}>
            Новая накладная
          </Button>
        )}
      </div>
      {error && <Alert>{error}</Alert>}
      {editing ? (
        <Card>
          <form
            noValidate
            className="form-stack"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <h2>Новая накладная</h2>
            <fieldset className="plain-fieldset form-stack" disabled={op.busy}>
              <div className="report-filters">
                <Input
                  label="Номер накладной"
                  required
                  maxLength={100}
                  value={number}
                  onChange={(e) => setNumber(e.target.value)}
                />
                <Input
                  label="Дата прихода (Астана)"
                  type="datetime-local"
                  required
                  value={received}
                  onChange={(e) => setReceived(e.target.value)}
                />
                {(["supplier", "warehouse", "payment_method"] as const).map(
                  (k) => (
                    <div key={k}>
                      <Select
                        label={labels[k]}
                        required
                        value={selected[k]}
                        onChange={(e) => setters[k](e.target.value)}
                      >
                        <option value="">Выберите</option>
                        {directories[k].map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.name}
                          </option>
                        ))}
                      </Select>
                      <Button
                        variant="ghost"
                        icon="plus"
                        onClick={() => setCreate(k)}
                      >
                        Добавить
                      </Button>
                    </div>
                  ),
                )}
              </div>
              <div className="button-row">
                <h3>Товары</h3>
                <Button
                  variant="secondary"
                  icon="plus"
                  onClick={() => setCreate("product")}
                >
                  Создать товар
                </Button>
              </div>
              {rows.map((row, index) => (
                <div className="invoice-line" key={row.id}>
                  <Select
                    label={`Товар ${index + 1}`}
                    required
                    value={row.item_id}
                    onChange={(e) =>
                      patch(row.id, {
                        item_id: e.target.value,
                        price: String(
                          (items.find((i) => i.id === e.target.value)
                            ?.purchase_price_minor || 0) / 100,
                        ),
                        unit:
                          items.find((i) => i.id === e.target.value)?.unit ||
                          "pcs",
                      })
                    }
                  >
                    <option value="">Выберите товар</option>
                    {items
                      .filter((i) => i.kind !== "prepared")
                      .map((i) => (
                        <option key={i.id} value={i.id}>
                          {i.name}
                          {i.barcode ? ` · ${i.barcode}` : ""}
                        </option>
                      ))}
                  </Select>
                  <Input
                    label={`Количество, ${t.units[row.unit as keyof typeof t.units]}`}
                    required
                    inputMode="decimal"
                    value={row.quantity}
                    onChange={(e) =>
                      patch(row.id, { quantity: e.target.value })
                    }
                  />
                  <Input
                    label="Цена за единицу, ₸"
                    required
                    inputMode="decimal"
                    value={row.price}
                    onChange={(e) => patch(row.id, { price: e.target.value })}
                  />
                  <Input
                    label="Годен до (Астана)"
                    required
                    type="datetime-local"
                    value={row.expires}
                    onChange={(e) => patch(row.id, { expires: e.target.value })}
                  />
                  <strong>
                    {stockMoney(invoiceLineCost(row.quantity, row.price) ?? 0)}
                  </strong>
                  <IconButton
                    icon="close"
                    label={`Удалить строку ${index + 1}`}
                    disabled={rows.length === 1}
                    onClick={() =>
                      setRows((rs) => rs.filter((r) => r.id !== row.id))
                    }
                  />
                </div>
              ))}
              <Button
                variant="secondary"
                icon="plus"
                disabled={rows.length >= 100}
                onClick={() => setRows((rs) => [...rs, fresh()])}
              >
                Добавить строку
              </Button>
              <div className="report-filters">
                <Input
                  label="Дополнительные расходы, ₸"
                  inputMode="decimal"
                  value={expenses}
                  onChange={(e) => setExpenses(e.target.value)}
                />
                <Input
                  label="Комментарий к расходам и накладной"
                  maxLength={200}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </div>
              <Input
                label="Оплачено сейчас, ₸"
                inputMode="decimal"
                placeholder={`Полностью — ${stockMoney(goods + (extra || 0))}`}
                value={paidNow}
                onChange={(e) => setPaidNow(e.target.value)}
                hint="Оставьте пустым, если оплачено полностью. Остаток станет долгом поставщику."
              />
              <div className="invoice-totals">
                <span>Товары: {stockMoney(goods)}</span>
                <span>Расходы: {stockMoney(extra || 0)}</span>
                <strong>Итого: {stockMoney(goods + (extra || 0))}</strong>
                {paid !== undefined && paid < goods + (extra || 0) && (
                  <strong className="debt">
                    Долг поставщику: {stockMoney(goods + (extra || 0) - paid)}
                  </strong>
                )}
              </div>
            </fieldset>
            {op.error && <Alert>{op.error}</Alert>}
            <div className="button-row">
              <Button type="submit" loading={op.busy}>
                Провести приход
              </Button>
              <Button
                variant="secondary"
                disabled={op.busy}
                onClick={() => setEditing(false)}
              >
                Закрыть форму
              </Button>
            </div>
          </form>
        </Card>
      ) : loading ? (
        <LoadingState />
      ) : (
        <>
          <div className="compact-list">
            {invoices.map((i) => (
              <Card key={i.id} className="compact-record">
                <div>
                  <h3>
                    № {i.number} · {i.supplier_name}
                  </h3>
                  <p className="muted">
                    {stockDate(i.received_at)} · {i.warehouse_name}
                  </p>
                </div>
                <div className="invoice-amount">
                  <strong>{stockMoney(i.total_minor)}</strong>
                  {i.debt_minor > 0 && (
                    <small className="debt">
                      долг {stockMoney(i.debt_minor)}
                    </small>
                  )}
                </div>
                {i.debt_minor > 0 && (
                  <Button variant="secondary" onClick={() => setPaying(i)}>
                    Оплатить долг
                  </Button>
                )}
                <DetailsButton title={`Накладная № ${i.number}`}>
                  <p>
                    {i.supplier_name} · {i.warehouse_name} ·{" "}
                    {i.payment_method_name}
                  </p>
                  {i.lines.map((l, index) => (
                    <p key={index}>
                      {String(l.name)} · {String(l.quantity)} ×{" "}
                      {stockMoney(Number(l.unit_cost_minor))} ={" "}
                      {stockMoney(Number(l.total_cost_minor))}
                    </p>
                  ))}
                  <p>Товары: {stockMoney(i.goods_minor)}</p>
                  <p>Расходы: {stockMoney(i.expenses_minor)}</p>
                  <strong>Итого: {stockMoney(i.total_minor)}</strong>
                  <p>
                    Оплачено: {stockMoney(i.paid_minor)}
                    {i.debt_minor > 0 && ` · долг ${stockMoney(i.debt_minor)}`}
                  </p>
                  <p>{i.note}</p>
                </DetailsButton>
              </Card>
            ))}
          </div>
          {paying && (
            <PayDebtDialog
              invoice={paying}
              methods={directories.payment_method}
              onClose={() => setPaying(null)}
              onDone={() => {
                setPaying(null);
                setAttempt((n) => n + 1);
              }}
            />
          )}
          {!invoices.length && (
            <p>
              Накладных пока нет. Старые одиночные приходы сохранены в истории
              партий.
            </p>
          )}
          <div className="stock-pagination">
            <Button
              variant="secondary"
              disabled={!offset}
              onClick={() => setOffset((n) => n - 20)}
            >
              Назад
            </Button>
            <Button
              variant="secondary"
              disabled={invoices.length < 20}
              onClick={() => setOffset((n) => n + 20)}
            >
              Далее
            </Button>
          </div>
        </>
      )}
      {create && (
        <Dialog
          open
          title={
            create === "product"
              ? "Создать товар"
              : `Добавить: ${labels[create].toLowerCase()}`
          }
          onClose={() => setCreate(null)}
        >
          {create === "product" ? (
            <ItemForm
              receiving
              onExpired={onExpired}
              onSaved={() => {
                setCreate(null);
                setAttempt((n) => n + 1);
              }}
              onCreated={(id, unit, purchasePrice) => {
                setRows((rs) => {
                  const empty = rs.find((r) => !r.item_id);
                  return empty
                    ? rs.map((r) =>
                        r.id === empty.id
                          ? {
                              ...r,
                              item_id: id,
                              unit,
                              price: String(purchasePrice / 100),
                            }
                          : r,
                      )
                    : [
                        ...rs,
                        {
                          ...fresh(),
                          item_id: id,
                          unit,
                          price: String(purchasePrice / 100),
                        },
                      ];
                });
              }}
            />
          ) : (
            <DirectoryForm
              kind={create}
              onExpired={onExpired}
              onSaved={(id) => {
                setters[create](id);
                setCreate(null);
                setAttempt((n) => n + 1);
              }}
            />
          )}
        </Dialog>
      )}
    </div>
  );
}

function PayDebtDialog({
  invoice,
  methods,
  onClose,
  onDone,
}: {
  invoice: Invoice;
  methods: Directory[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [amount, setAmount] = useState(String(invoice.debt_minor / 100)),
    [method, setMethod] = useState(methods[0]?.id ?? ""),
    [paidAt, setPaidAt] = useState(almatyNow()),
    [note, setNote] = useState("");
  const op = useOperation(() => window.location.reload());
  async function submit() {
    const minor = costMinor(amount),
      time = almatyInstant(paidAt);
    if (!minor || minor > invoice.debt_minor) {
      op.setFields({ amount_minor: "Сумма от 0,01 ₸ до суммы долга" });
      return;
    }
    if (!method || !time) {
      op.setError("Выберите способ оплаты и дату");
      return;
    }
    const body = {
      amount_minor: minor,
      payment_method_id: method,
      paid_at: time,
      note,
    };
    if (
      await op.run({ invoice: invoice.id, ...body }, (key) =>
        receivingApi.pay(invoice.id, body, key),
      )
    )
      onDone();
  }
  return (
    <Dialog
      open
      title={`Оплата долга · № ${invoice.number}`}
      busy={op.busy}
      onClose={onClose}
    >
      <form
        className="form-stack"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <p>
          {invoice.supplier_name}: долг{" "}
          <strong>{stockMoney(invoice.debt_minor)}</strong>
        </p>
        <Input
          label="Сумма, ₸"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          error={op.fields.amount_minor}
          required
        />
        <Select
          label="Способ оплаты"
          value={method}
          onChange={(e) => setMethod(e.target.value)}
        >
          {methods.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </Select>
        <Input
          label="Дата оплаты (Астана)"
          type="datetime-local"
          value={paidAt}
          onChange={(e) => setPaidAt(e.target.value)}
          error={op.fields.paid_at}
        />
        <Input
          label="Комментарий"
          maxLength={200}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        {op.error && <Alert>{op.error}</Alert>}
        <Button type="submit" loading={op.busy}>
          Оплатить
        </Button>
      </form>
    </Dialog>
  );
}
