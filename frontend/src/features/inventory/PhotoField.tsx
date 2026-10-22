import { useState } from "react";
import { inventoryApi, type StockItem } from "../../shared/api/inventory";
import { errorMessage } from "../../shared/lib/forms";
import { Button } from "../../shared/ui/Button";
import { FoodArt } from "../../shared/ui/FoodArt";

/** Photo of an existing menu product; the server resizes it and strips metadata. */
export function PhotoField({
  item,
  onChanged,
}: {
  item: StockItem;
  onChanged: () => void;
}) {
  const [digest, setDigest] = useState(item.image),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError("");
    try {
      setDigest(await action());
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="field">
      <span className="field-label">Фото для меню</span>
      <div className="photo-field">
        {digest ? (
          <img
            src={`/api/v1/inventory/items/${item.id}/image?v=${digest.slice(0, 16)}`}
            alt={`Фото: ${item.name}`}
          />
        ) : (
          <FoodArt category={item.category} name={item.name} />
        )}
        <div className="form-stack">
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            aria-label="Выбрать фото"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void run(() => inventoryApi.setImage(item.id, file));
            }}
          />
          {digest && (
            <Button
              variant="ghost"
              loading={busy}
              onClick={() =>
                void run(async () => {
                  await inventoryApi.removeImage(item.id);
                  return "";
                })
              }
            >
              Убрать фото
            </Button>
          )}
          <small className="field-hint">JPEG, PNG или WebP до 8 МБ.</small>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
