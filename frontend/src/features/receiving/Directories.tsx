import { useEffect, useState } from "react";
import {
  receivingApi,
  type Directory,
  type DirectoryDetails,
  type DirectoryKind,
} from "../../shared/api/receiving";
import { useOperation } from "../../shared/lib/useOperation";
import { errorMessage } from "../../shared/lib/forms";
import { Button, IconButton } from "../../shared/ui/Button";
import { Input } from "../../shared/ui/Input";
import { Alert, Card } from "../../shared/ui/Feedback";
import { Dialog } from "../../shared/ui/Dialog";
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
type Mode = "view" | "edit" | "delete";
const modeTitles: Record<Mode, string> = {
  view: "Просмотр",
  edit: "Изменить название",
  delete: "Удалить запись",
};
// Preview, rename and delete of one settings entry; a used entry is only renamed.
function EntryDialog({
  entry,
  mode,
  kindLabel,
  onMode,
  onClose,
  onSaved,
  onExpired,
}: {
  entry: Directory;
  mode: Mode;
  kindLabel: string;
  onMode: (mode: Mode) => void;
  onClose: () => void;
  onSaved: () => void;
  onExpired: () => void;
}) {
  const [details, setDetails] = useState<DirectoryDetails | null>(null);
  const [loadError, setLoadError] = useState("");
  const [name, setName] = useState(entry.name);
  const op = useOperation(onExpired);
  useEffect(() => {
    let active = true;
    void receivingApi
      .directory(entry.id)
      .then((d) => active && setDetails(d))
      .catch((e) => active && setLoadError(errorMessage(e)));
    return () => {
      active = false;
    };
  }, [entry.id]);
  const usage = Object.entries(details?.usage ?? {});
  const locked = entry.system || usage.length > 0;
  return (
    <Dialog
      open
      title={`${modeTitles[mode]}: ${entry.name}`}
      onClose={onClose}
      busy={op.busy}
    >
      {loadError && <Alert>{loadError}</Alert>}
      {mode === "view" && (
        <div className="form-stack">
          <p className="muted">
            {kindLabel}
            {entry.system && " · системная запись"}
          </p>
          {entry.kind === "payment_method" && (
            <p>
              Комиссия банка:{" "}
              {(entry.commission_bp / 100).toLocaleString("ru-RU")}%
            </p>
          )}
          <h3>Где используется</h3>
          {!details ? (
            <p className="muted">Загрузка…</p>
          ) : usage.length ? (
            <ul className="stock-items">
              {usage.map(([label, count]) => (
                <li key={label} className="directory-usage">
                  {label}
                  <strong>{count}</strong>
                </li>
              ))}
            </ul>
          ) : (
            <p>Нигде не используется — запись можно удалить.</p>
          )}
          <div className="dialog-actions">
            <Button variant="secondary" onClick={() => onMode("edit")}>
              Изменить
            </Button>
            <Button
              variant="danger"
              disabled={!details || locked}
              onClick={() => onMode("delete")}
            >
              Удалить
            </Button>
          </div>
        </div>
      )}
      {mode === "edit" && (
        <form
          className="form-stack"
          onSubmit={(e) => {
            e.preventDefault();
            void op
              .run({ id: entry.id, name }, (key) =>
                receivingApi.renameDirectory(entry.id, name, key),
              )
              .then((ok) => ok && onSaved());
          }}
        >
          <Input
            label="Название"
            value={name}
            required
            maxLength={entry.kind === "category" ? 60 : 100}
            onChange={(e) => setName(e.target.value)}
            error={op.fields.name}
            hint={
              entry.kind === "category"
                ? "Новое название появится у всех товаров и в меню этой категории."
                : "История (накладные, чеки) сохраняет название на момент операции."
            }
          />
          {op.error && <Alert>{op.error}</Alert>}
          <div className="dialog-actions">
            <Button
              variant="secondary"
              disabled={op.busy}
              onClick={() => onMode("view")}
            >
              Назад
            </Button>
            <Button
              type="submit"
              loading={op.busy}
              disabled={!name.trim() || name.trim() === entry.name}
            >
              Сохранить
            </Button>
          </div>
        </form>
      )}
      {mode === "delete" && (
        <div className="form-stack">
          {entry.system ? (
            <Alert>
              Системную запись нельзя удалить, только переименовать.
            </Alert>
          ) : usage.length ? (
            <Alert>
              Запись используется (
              {usage.map(([l, n]) => `${l}: ${n}`).join(", ")}) — её можно
              только переименовать.
            </Alert>
          ) : (
            <p>
              Удалить «{entry.name}»? Запись нигде не используется, действие
              нельзя отменить.
            </p>
          )}
          {op.error && <Alert>{op.error}</Alert>}
          <div className="dialog-actions">
            <Button
              variant="secondary"
              disabled={op.busy}
              onClick={() => onMode("view")}
            >
              Отмена
            </Button>
            <Button
              variant="danger"
              icon="trash"
              loading={op.busy}
              disabled={!details || locked}
              onClick={() =>
                void op
                  .run({ delete: entry.id }, (key) =>
                    receivingApi.deleteDirectory(entry.id, key),
                  )
                  .then((ok) => ok && onSaved())
              }
            >
              Удалить
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
export function Directories({ onExpired }: { onExpired: () => void }) {
  const [kind, setKind] = useState<DirectoryKind>("payment_method");
  const [rows, setRows] = useState<Directory[]>([]);
  const [open, setOpen] = useState<{ entry: Directory; mode: Mode } | null>(
    null,
  );
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
          <div className="staff-directory">
            {rows.map((d) => (
              <div key={d.id}>
                <span>
                  <strong>{d.name}</strong>
                  {d.system && <small>Системная запись</small>}
                </span>
                <span className="row-actions">
                  <IconButton
                    variant="ghost"
                    icon="eye"
                    label={`Просмотр: ${d.name}`}
                    onClick={() => setOpen({ entry: d, mode: "view" })}
                  />
                  <IconButton
                    variant="ghost"
                    icon="edit"
                    label={`Изменить: ${d.name}`}
                    onClick={() => setOpen({ entry: d, mode: "edit" })}
                  />
                  <IconButton
                    variant="ghost"
                    icon="trash"
                    label={`Удалить: ${d.name}`}
                    disabled={d.system}
                    onClick={() => setOpen({ entry: d, mode: "delete" })}
                  />
                </span>
              </div>
            ))}
          </div>
          {!rows.length && <p>Пока нет записей</p>}
        </Card>
      </div>
      {open && (
        <EntryDialog
          key={open.entry.id}
          entry={open.entry}
          mode={open.mode}
          kindLabel={labels[kind]}
          onMode={(mode) => setOpen({ ...open, mode })}
          onClose={() => setOpen(null)}
          onSaved={() => {
            setOpen(null);
            setAttempt((n) => n + 1);
          }}
          onExpired={onExpired}
        />
      )}
    </div>
  );
}
