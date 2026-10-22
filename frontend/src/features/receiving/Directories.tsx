import { useEffect, useState } from "react";
import {
  receivingApi,
  type Directory,
  type DirectoryKind,
} from "../../shared/api/receiving";
import { useOperation } from "../../shared/lib/useOperation";
import { errorMessage } from "../../shared/lib/forms";
import { Button } from "../../shared/ui/Button";
import { Input } from "../../shared/ui/Input";
import { Alert, Card } from "../../shared/ui/Feedback";
export function DirectoryForm({
  kind,
  onSaved,
  onExpired,
}: {
  kind: DirectoryKind;
  onSaved: (id: string) => void;
  onExpired: () => void;
}) {
  const [name, setName] = useState("");
  const op = useOperation(onExpired);
  return (
    <form
      className="form-stack"
      onSubmit={(e) => {
        e.preventDefault();
        void op.run({ kind, name }, async (key) => {
          const result = await receivingApi.createDirectory(kind, name, key);
          onSaved(result.subject_id);
        });
      }}
    >
      <Input
        label="Название"
        value={name}
        required
        maxLength={100}
        onChange={(e) => setName(e.target.value)}
        error={op.fields.name}
      />
      {op.error && <Alert>{op.error}</Alert>}
      <Button type="submit" icon="plus" loading={op.busy}>
        Создать
      </Button>
    </form>
  );
}
const labels: Record<DirectoryKind, string> = {
  supplier: "Поставщики",
  warehouse: "Склады",
  payment_method: "Способы оплаты",
  category: "Категории",
  expense_category: "Статьи расходов",
};
export function Directories({ onExpired }: { onExpired: () => void }) {
  const [kind, setKind] = useState<DirectoryKind>("payment_method");
  const [rows, setRows] = useState<Directory[]>([]);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    void receivingApi
      .directories(kind)
      .then((r) => {
        if (active) {
          setRows(r);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [kind, attempt]);
  return (
    <div className="form-stack">
      <h1>Настройки</h1>
      <div className="button-row">
        {Object.entries(labels).map(([k, label]) => (
          <Button
            key={k}
            variant={kind === k ? "primary" : "secondary"}
            onClick={() => setKind(k as DirectoryKind)}
          >
            {label}
          </Button>
        ))}
      </div>
      {error && <Alert>{error}</Alert>}
      <div className="stock-columns">
        <Card>
          <h2>Добавить: {labels[kind].toLowerCase()}</h2>
          <DirectoryForm
            key={kind}
            kind={kind}
            onExpired={onExpired}
            onSaved={() => setAttempt((n) => n + 1)}
          />
        </Card>
        <Card>
          <h2>{labels[kind]}</h2>
          <ul className="stock-items">
            {rows.map((d) => (
              <li key={d.id}>{d.name}</li>
            ))}
          </ul>
          {!rows.length && <p>Пока нет записей</p>}
        </Card>
      </div>
    </div>
  );
}
