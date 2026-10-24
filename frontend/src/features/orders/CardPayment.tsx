import { useState } from "react";
import { shortMoney } from "../../shared/lib/inventory-validation";
import {
  formatCardNumber,
  formatExpiry,
  validateTestCard,
  type CardErrors,
  type TestCardOutcome,
} from "../../shared/lib/test-card";
import { Button } from "../../shared/ui/Button";
import { Dialog } from "../../shared/ui/Dialog";
import { Alert } from "../../shared/ui/Feedback";
import { Input } from "../../shared/ui/Input";

export function CardPayment({
  total,
  busy,
  error,
  onPay,
  onClose,
}: {
  total: number;
  busy: boolean;
  error: string;
  onPay: (outcome: TestCardOutcome) => void;
  onClose: () => void;
}) {
  const [number, setNumber] = useState(""),
    [expiry, setExpiry] = useState(""),
    [cvc, setCvc] = useState(""),
    [errors, setErrors] = useState<CardErrors>({});
  return (
    <Dialog
      open
      title="Оплата картой"
      className="card-sheet"
      busy={busy}
      onClose={onClose}
    >
      <form
        className="form-stack"
        noValidate
        // Card fields are local only: nothing below is submitted to the server.
        autoComplete="off"
        onSubmit={(e) => {
          e.preventDefault();
          const result = validateTestCard(number, expiry, cvc);
          setErrors(result.errors);
          if (result.outcome) onPay(result.outcome);
        }}
      >
        <div className="bank-card" aria-hidden="true">
          <span className="bank-card-chip" />
          <strong>{formatCardNumber(number) || "•••• •••• •••• ••••"}</strong>
          <span>{expiry || "ММ/ГГ"}</span>
        </div>
        <Input
          label="Номер карты"
          inputMode="numeric"
          autoComplete="off"
          placeholder="0000 0000 0000 0000"
          value={formatCardNumber(number)}
          onChange={(e) => setNumber(e.target.value)}
          error={errors.number}
          disabled={busy}
          required
        />
        <div className="stock-form-grid">
          <Input
            label="Срок действия"
            inputMode="numeric"
            autoComplete="off"
            placeholder="ММ/ГГ"
            value={expiry}
            onChange={(e) => setExpiry(formatExpiry(e.target.value))}
            error={errors.expiry}
            disabled={busy}
            required
          />
          <Input
            label="CVV"
            inputMode="numeric"
            autoComplete="off"
            placeholder="123"
            maxLength={3}
            value={cvc}
            onChange={(e) => setCvc(e.target.value.replace(/\D/g, ""))}
            error={errors.cvc}
            disabled={busy}
            required
          />
        </div>
        <p className="test-card-note">
          Тестовый режим: карта 4242 4242 4242 4242, любой будущий срок и CVV.{" "}
          <button
            type="button"
            className="link-button"
            onClick={() => {
              setNumber("4242424242424242");
              setExpiry("12/30");
              setCvc("123");
              setErrors({});
            }}
          >
            Заполнить
          </button>
        </p>
        {error && <Alert>{error}</Alert>}
        <p className="field-hint">
          Заказы с сайта оплачиваются только картой. После оплаты заказ нельзя
          отменить, деньги не возвращаются.
        </p>
        <Button type="submit" loading={busy} className="full-width">
          Оплатить {shortMoney(total)}
        </Button>
      </form>
    </Dialog>
  );
}
