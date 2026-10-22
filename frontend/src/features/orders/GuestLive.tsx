import { useState } from "react";
import { GUEST_EVENTS, useLiveReload } from "../../shared/lib/live-events";
import { orderNumber } from "../../shared/lib/pickup-qr";
import { Icon } from "../../shared/ui/Icon";

const news: Record<string, string> = {
  preparing: "собирается",
  ready: "готов! Покажите QR-код на стойке выдачи",
  completed: "выдан. Приятного аппетита!",
};

/** Updates the guest's orders the moment the kitchen changes their status. */
export function GuestLive({ onReload }: { onReload: () => void }) {
  const [message, setMessage] = useState("");
  useLiveReload(
    ["orders"],
    onReload,
    (event) => {
      const text = news[event.kind];
      if (!text || !event.id) return;
      setMessage(`Заказ №${orderNumber(event.id)} ${text}`);
      if (event.kind === "ready") navigator.vibrate?.([200, 100, 200]);
    },
    GUEST_EVENTS,
  );
  if (!message) return null;
  return (
    <div className="incoming" role="status">
      <Icon name="bell" />
      <div>
        <strong>{message}</strong>
      </div>
    </div>
  );
}
