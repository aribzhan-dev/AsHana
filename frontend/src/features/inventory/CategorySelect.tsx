import { useEffect, useRef, useState } from "react";
import { receivingApi, type Directory } from "../../shared/api/receiving";
import { errorMessage } from "../../shared/lib/forms";
import { Button } from "../../shared/ui/Button";
import { Input, Select } from "../../shared/ui/Input";

const NEW = "__new__";

// One shared category list: staff pick an existing name or add it once for everyone.
export function CategorySelect({
  value,
  onChange,
  error,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  error?: string;
  disabled?: boolean;
}) {
  const [items, setItems] = useState<Directory[] | null>(null),
    [loadError, setLoadError] = useState(""),
    [adding, setAdding] = useState(false),
    [name, setName] = useState(""),
    [createError, setCreateError] = useState(""),
    [busy, setBusy] = useState(false);
  const key = useRef<{ name: string; key: string } | null>(null);
  useEffect(() => {
    let active = true;
    receivingApi
      .directories("category")
      .then((list) => {
        if (active) setItems(list);
      })
      .catch((cause) => {
        if (active) setLoadError(errorMessage(cause));
      });
    return () => {
      active = false;
    };
  }, []);
  const known = items?.some((c) => c.name === value) ?? true;

  async function create() {
    const trimmed = name.trim();
    if (!trimmed) {
      setCreateError("Введите название категории");
      return;
    }
    const existing = items?.find(
      (c) => c.name.toLocaleLowerCase("ru") === trimmed.toLocaleLowerCase("ru"),
    );
    if (existing) {
      onChange(existing.name);
      setAdding(false);
      return;
    }
    if (key.current?.name !== trimmed)
      key.current = { name: trimmed, key: crypto.randomUUID() };
    setBusy(true);
    setCreateError("");
    try {
      await receivingApi.createDirectory("category", trimmed, key.current.key);
      const list = await receivingApi.directories("category");
      setItems(list);
      onChange(
        list.find(
          (c) =>
            c.name.toLocaleLowerCase("ru") === trimmed.toLocaleLowerCase("ru"),
        )?.name ?? trimmed,
      );
      setAdding(false);
      setName("");
      key.current = null;
    } catch (cause) {
      setCreateError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="category-select">
      <Select
        label="Категория"
        value={adding ? NEW : value}
        disabled={disabled || !items}
        error={error || loadError}
        onChange={(e) => {
          if (e.target.value === NEW) {
            setAdding(true);
            return;
          }
          setAdding(false);
          onChange(e.target.value);
        }}
      >
        <option value="">Без категории</option>
        {!known && value && <option value={value}>{value}</option>}
        {items?.map((c) => (
          <option key={c.id} value={c.name}>
            {c.name}
          </option>
        ))}
        <option value={NEW}>＋ Новая категория…</option>
      </Select>
      {adding && (
        <div className="category-create">
          <Input
            label="Новая категория"
            value={name}
            maxLength={60}
            autoFocus
            placeholder="Например, Напитки"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void create();
              }
            }}
            error={createError}
            disabled={busy}
          />
          <div className="button-row">
            <Button loading={busy} onClick={() => void create()}>
              Создать
            </Button>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => {
                setAdding(false);
                setCreateError("");
              }}
            >
              Отмена
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
