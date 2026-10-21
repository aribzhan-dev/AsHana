import { displayText } from "../../shared/lib/display-text";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  inventoryApi,
  type StockBatch,
  type StockChange,
  type StockMovement,
} from "../../shared/api/inventory";
import { ApiError } from "../../shared/api/http";
import { Dialog } from "../../shared/ui/Dialog";
import { Button } from "../../shared/ui/Button";
import { Input, Select } from "../../shared/ui/Input";
import {
  Alert,
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../shared/ui/Feedback";
import { errorMessage, focusInvalid } from "../../shared/lib/forms";
import {
  decimalText,
  stockDate,
  stockNumber,
  stockQuantityError,
} from "../../shared/lib/inventory-validation";
import { inventoryRu as t } from "../../shared/locales/inventory";
import { useStockMutation } from "./useStockMutation";

export function BatchDialog({
  batch,
  operation,
  onClose,
  onSaved,
  onExpired,
  change = inventoryApi.change,
}: {
  change?: typeof inventoryApi.change;
  batch: StockBatch;
  operation: StockChange["operation"];
  onClose: () => void;
  onSaved: () => void;
  onExpired: () => void;
}) {
  const [unit, setUnit] = useState(batch.unit);
  const units =
    batch.unit === "kg"
      ? ["kg", "g"]
      : batch.unit === "l"
        ? ["l", "ml"]
        : [batch.unit];
  const [amount, setAmount] = useState(""),
    [reason, setReason] = useState("");
  const mutation = useStockMutation(onExpired),
    numeric = operation === "write_off" || operation === "count";
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = {
      reason: reason.trim() ? "" : t.required,
      quantity: numeric
        ? stockQuantityError(amount, unit, operation === "count") || ""
        : "",
    };
    mutation.setFields(errors);
    mutation.setError("");
    if (Object.values(errors).some(Boolean)) {
      focusInvalid(event.currentTarget);
      return;
    }
    const data: StockChange = {
      operation,
      quantity: numeric ? decimalText(amount) : null,
      unit: numeric ? (unit as StockChange["unit"]) : null,
      reason: reason.trim(),
      expected_version: batch.version,
    };
    if (
      await mutation.run({ id: batch.id, ...data }, (key) =>
        change(batch.id, data, key),
      )
    ) {
      onSaved();
      onClose();
    }
  }
  return (
    <Dialog
      open
      title={t.actions[operation]}
      description={`${batch.item_name} · ${displayText(batch.label)}`}
      onClose={onClose}
      busy={mutation.busy}
    >
      <p>
        {t.onHand}:{" "}
        <strong>
          {stockNumber(batch.on_hand)}{" "}
          {t.units[batch.unit as keyof typeof t.units]}
        </strong>{" "}
        · {t.version} {batch.version}
      </p>
      <p className="field-hint">{t.stockHint}</p>
      <form
        noValidate
        onSubmit={(e) => void submit(e)}
        aria-label={t.actions[operation]}
      >
        <fieldset className="form-fields" disabled={mutation.busy}>
          {numeric && (
            <Input
              label={operation === "count" ? t.actual : t.quantity}
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              error={mutation.fields.quantity}
              maxLength={24}
              hint={t.quantityHint}
              placeholder="0"
              required
            />
          )}
          {numeric && (
            <Select
              label={t.unit}
              value={unit}
              error={mutation.fields.unit}
              onChange={(e) => setUnit(e.target.value)}
            >
              {units.map((code) => (
                <option key={code} value={code}>
                  {t.units[code as keyof typeof t.units]}
                </option>
              ))}
            </Select>
          )}
          <Input
            label={t.reason}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            error={mutation.fields.reason}
            placeholder={t.reasonPlaceholder}
            maxLength={200}
            required
          />
        </fieldset>
        {mutation.error && (
          <Alert>
            <p>{mutation.error}</p>
            <p>{t.staleHint}</p>
          </Alert>
        )}
        <div className="dialog-actions">
          <Button
            variant="secondary"
            disabled={mutation.busy}
            onClick={onClose}
          >
            {t.cancel}
          </Button>
          <Button
            type="submit"
            variant={operation === "write_off" ? "danger" : "primary"}
            loading={mutation.busy}
          >
            {t.confirm}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function HistoryDialog({
  batch,
  onClose,
  onExpired,
}: {
  batch: StockBatch;
  onClose: () => void;
  onExpired: () => void;
}) {
  const [rows, setRows] = useState<StockMovement[]>([]),
    [page, setPage] = useState(0),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    void inventoryApi
      .movements(batch.id, page * 20)
      .then((data) => {
        if (active) setRows(data);
      })
      .catch((cause) => {
        if (!active) return;
        if (cause instanceof ApiError && cause.status === 401) onExpired();
        else setError(errorMessage(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [batch.id, page, attempt, onExpired]);
  function changePage(next: number) {
    setPage(next);
    setLoading(true);
    setError("");
  }
  return (
    <Dialog
      open
      title={t.history}
      description={`${batch.item_name} · ${displayText(batch.label)}`}
      onClose={onClose}
    >
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState
          message={error}
          onRetry={() => {
            setLoading(true);
            setError("");
            setAttempt((value) => value + 1);
          }}
        />
      ) : !rows.length ? (
        <EmptyState title={t.noMovements} />
      ) : (
        <ol className="stock-history">
          {rows.map((row) => (
            <li key={row.id}>
              <strong>{t.actions[row.action as keyof typeof t.actions]}</strong>
              <p>
                {stockDate(row.created_at)} · {t.version} {row.version}
              </p>
              <p>
                {t.before}: {stockNumber(row.before)} → {t.after}:{" "}
                {stockNumber(row.after)}{" "}
                {t.units[batch.unit as keyof typeof t.units]}
              </p>
              <p>{displayText(row.reason)}</p>
              <small>
                {t.author}: {row.actor_id}
              </small>
            </li>
          ))}
        </ol>
      )}
      <div className="stock-pagination">
        <Button
          variant="secondary"
          disabled={loading || page === 0}
          onClick={() => changePage(page - 1)}
        >
          {t.previous}
        </Button>
        <span>
          {t.page} {page + 1}
        </span>
        <Button
          variant="secondary"
          disabled={loading || rows.length < 20}
          onClick={() => changePage(page + 1)}
        >
          {t.next}
        </Button>
      </div>
    </Dialog>
  );
}
