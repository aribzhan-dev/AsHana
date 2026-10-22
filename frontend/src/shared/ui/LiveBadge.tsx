import type { LiveStatus } from "../lib/live-events";

const labels: Record<LiveStatus, string> = {
  live: "Обновляется сразу",
  connecting: "Подключаемся…",
  offline: "Нет связи — обновляем каждые 15 секунд",
};

export function LiveBadge({ status }: { status: LiveStatus }) {
  return (
    <span className={`live-badge live-${status}`} role="status">
      <i aria-hidden="true" />
      {labels[status]}
    </span>
  );
}
