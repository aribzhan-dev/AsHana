import { useEffect, useState } from "react";
import { financeApi, type MyShift as Shift } from "../../shared/api/finance";
import { stockDate } from "../../shared/lib/inventory-validation";
import { useOperation } from "../../shared/lib/useOperation";
import { Button } from "../../shared/ui/Button";
import { Alert, Card } from "../../shared/ui/Feedback";

/** Check-in/out for staff whose account is linked to a payroll worker. */
export function MyShift() {
  const [shift, setShift] = useState<Shift | null>(null),
    [attempt, setAttempt] = useState(0);
  const op = useOperation(() => window.location.reload());
  useEffect(() => {
    let alive = true;
    financeApi
      .myShift()
      .then((s) => {
        if (alive) setShift(s);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [attempt]);
  if (!shift?.linked) return null;
  const started = shift.started_at;
  return (
    <Card className="shift-card">
      <div>
        <h2>Смена</h2>
        <p className="muted">
          {started
            ? `Идёт с ${stockDate(started)}`
            : "Отметьте начало смены, когда придёте на работу."}
        </p>
      </div>
      <Button
        variant={started ? "secondary" : "primary"}
        icon="clock"
        loading={op.busy}
        onClick={() =>
          void op
            .run({ start: !started, at: attempt }, (key) =>
              financeApi.toggleShift(!started, key),
            )
            .then((ok) => ok && setAttempt((n) => n + 1))
        }
      >
        {started ? "Завершить смену" : "Начать смену"}
      </Button>
      {op.error && <Alert>{op.error}</Alert>}
    </Card>
  );
}
