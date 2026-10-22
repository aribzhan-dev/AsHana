import { useEffect, useRef, useSyncExternalStore } from "react";

export type LiveTopic = "orders" | "pos" | "stock";
export type LiveEvent = { topic: LiveTopic; kind: string; id: string };
export type LiveStatus = "connecting" | "live" | "offline";

type Listener = (event: LiveEvent) => void;

// One socket per channel and page, shared by every screen section. The socket only says
// *what* changed; components reload the actual data over HTTP.
class Channel {
  socket: WebSocket | null = null;
  status: LiveStatus = "connecting";
  retry = 0;
  timer: number | undefined;
  listeners = new Set<Listener>();
  watchers = new Set<() => void>();
  constructor(readonly path: string) {}

  setStatus(next: LiveStatus) {
    if (this.status === next) return;
    this.status = next;
    this.watchers.forEach((w) => w());
  }

  emit(event: LiveEvent) {
    this.listeners.forEach((l) => l(event));
  }

  connect() {
    if (this.socket || !this.listeners.size) return;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(
      `${protocol}://${window.location.host}${this.path}`,
    );
    this.socket = ws;
    this.setStatus("connecting");
    ws.onopen = () => {
      this.retry = 0;
      this.setStatus("live");
      // Anything may have changed while disconnected: reload everything once.
      for (const topic of ["orders", "pos", "stock"] as const)
        this.emit({ topic, kind: "resync", id: "" });
    };
    ws.onmessage = (message) => {
      const event = parse(message.data);
      if (event) this.emit(event);
    };
    ws.onclose = (close) => {
      this.socket = null;
      this.setStatus("offline");
      // 4401/4403: not signed in or foreign origin — retry rarely, polling still works.
      const wait =
        close.code === 4401 || close.code === 4403
          ? 60_000
          : Math.min(30_000, 1000 * 2 ** this.retry++);
      if (this.listeners.size)
        this.timer = window.setTimeout(() => this.connect(), wait);
    };
  }

  disconnect() {
    window.clearTimeout(this.timer);
    this.timer = undefined;
    if (this.socket) {
      this.socket.onclose = null;
      this.socket.close();
      this.socket = null;
    }
    this.setStatus("connecting");
  }

  subscribe(listener: Listener) {
    this.listeners.add(listener);
    this.connect();
    return () => {
      this.listeners.delete(listener);
      if (!this.listeners.size) this.disconnect();
    };
  }
}

const channels = new Map<string, Channel>();
function channel(path: string) {
  let found = channels.get(path);
  if (!found) {
    found = new Channel(path);
    channels.set(path, found);
  }
  return found;
}
export const STAFF_EVENTS = "/api/v1/staff/events";
export const GUEST_EVENTS = "/api/v1/orders/live";

function parse(data: unknown): LiveEvent | null {
  if (typeof data !== "string") return null;
  try {
    const value: unknown = JSON.parse(data);
    if (
      typeof value === "object" &&
      value !== null &&
      "topic" in value &&
      ["orders", "pos", "stock"].includes(String(value.topic))
    ) {
      const v = value as Record<string, unknown>;
      return {
        topic: v.topic as LiveTopic,
        kind: typeof v.kind === "string" ? v.kind : "",
        id: typeof v.id === "string" ? v.id : "",
      };
    }
  } catch {
    // Malformed frames are ignored; polling keeps the screen correct.
  }
  return null;
}

export function useLiveStatus(path = STAFF_EVENTS): LiveStatus {
  const c = channel(path);
  return useSyncExternalStore(
    (watch) => {
      c.watchers.add(watch);
      return () => c.watchers.delete(watch);
    },
    () => c.status,
  );
}

/** Calls `handler` for change signals on the given topics; returns connection status. */
export function useLiveEvents(
  topics: LiveTopic[],
  handler: (event: LiveEvent) => void,
  path = STAFF_EVENTS,
): LiveStatus {
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  const key = topics.join(",");
  useEffect(() => {
    const wanted = new Set(key.split(","));
    return channel(path).subscribe((event) => {
      if (wanted.has(event.topic)) latest.current(event);
    });
  }, [key, path]);
  return useLiveStatus(path);
}

/**
 * Reloads on change signals (coalescing bursts) and keeps polling as a safety net:
 * every 15 s without a live connection, every 60 s with one.
 */
export function useLiveReload(
  topics: LiveTopic[],
  reload: () => void,
  onEvent?: (event: LiveEvent) => void,
  path = STAFF_EVENTS,
): LiveStatus {
  const latest = useRef(reload);
  useEffect(() => {
    latest.current = reload;
  });
  const pending = useRef<number | undefined>(undefined);
  const live = useLiveEvents(
    topics,
    (event) => {
      onEvent?.(event);
      window.clearTimeout(pending.current);
      pending.current = window.setTimeout(() => latest.current(), 300);
    },
    path,
  );
  useEffect(() => {
    const timer = window.setInterval(
      () => latest.current(),
      live === "live" ? 60_000 : 15_000,
    );
    return () => window.clearInterval(timer);
  }, [live]);
  // Separate from the interval: a status change must not drop a queued reload.
  useEffect(() => () => window.clearTimeout(pending.current), []);
  return live;
}
