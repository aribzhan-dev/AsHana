import { useCallback, useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { ApiError } from "../../shared/api/http";
import { ordersApi, type Order } from "../../shared/api/orders";
import { errorMessage } from "../../shared/lib/forms";
import { stockDate, stockMoney } from "../../shared/lib/inventory-validation";
import {
  orderNumber,
  parsePickupPayload,
  type PickupScan,
} from "../../shared/lib/pickup-qr";
import { useOperation } from "../../shared/lib/useOperation";
import { Button } from "../../shared/ui/Button";
import { Alert, Badge } from "../../shared/ui/Feedback";
import { Icon } from "../../shared/ui/Icon";

const statuses: Record<Order["status"], string> = {
  pending_payment: "Ожидает оплаты",
  confirmed: "Принят, ещё не собран",
  preparing: "Комплектуется",
  ready: "Готов к выдаче",
  completed: "Уже выдан",
  cancelled: "Отменён",
  expired: "Резерв истёк",
  no_show: "Не забрали",
};

function useCamera(active: boolean, onCode: (raw: string) => void) {
  const video = useRef<HTMLVideoElement>(null);
  const supported = Boolean(navigator.mediaDevices?.getUserMedia);
  const [state, setState] = useState<"off" | "on" | "denied">("off");
  useEffect(() => {
    if (!active || !supported) return;
    let stream: MediaStream | undefined;
    let frame = 0;
    let stopped = false;
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d", { willReadFrequently: true });
    function tick() {
      const v = video.current;
      if (stopped || !v || !context) return;
      if (v.readyState >= 2 && v.videoWidth) {
        // Downscale frames: QR decoding does not need full camera resolution.
        const scale = Math.min(1, 640 / v.videoWidth);
        canvas.width = Math.round(v.videoWidth * scale);
        canvas.height = Math.round(v.videoHeight * scale);
        context.drawImage(v, 0, 0, canvas.width, canvas.height);
        const image = context.getImageData(0, 0, canvas.width, canvas.height);
        const found = jsQR(image.data, image.width, image.height, {
          inversionAttempts: "dontInvert",
        });
        if (found?.data) onCode(found.data);
      }
      frame = window.setTimeout(tick, 200);
    }
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then((media) => {
        if (stopped) return media.getTracks().forEach((t) => t.stop());
        stream = media;
        if (video.current) {
          video.current.srcObject = media;
          void video.current.play().catch(() => undefined);
        }
        setState("on");
        tick();
      })
      .catch(() => setState("denied"));
    return () => {
      stopped = true;
      window.clearTimeout(frame);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [active, supported, onCode]);
  return { video, state: supported ? state : "missing" };
}

export function PickupScanner({ permissions }: { permissions: string[] }) {
  const [scan, setScan] = useState<PickupScan | null>(null),
    [order, setOrder] = useState<Order | null>(null),
    [lookupError, setLookupError] = useState(""),
    [manual, setManual] = useState(""),
    [done, setDone] = useState<Order | null>(null),
    [camera, setCamera] = useState(false);
  const op = useOperation(() => window.location.reload());
  const last = useRef("");
  const input = useRef<HTMLInputElement>(null);
  const canIssue = permissions.includes("orders.fulfil");

  const accept = useCallback((raw: string) => {
    if (raw === last.current) return;
    last.current = raw;
    const parsed = parsePickupPayload(raw);
    setDone(null);
    setOrder(null);
    if (!parsed) {
      setScan(null);
      setLookupError("Это не QR-код заказа AsHana. Попросите открыть заказ.");
      return;
    }
    setLookupError("");
    setScan(parsed);
  }, []);
  const { video, state } = useCamera(camera && !scan, accept);

  useEffect(() => {
    if (!scan) return;
    let active = true;
    ordersApi
      .staffOrder(scan.orderId)
      .then((value) => {
        if (active) setOrder(value);
      })
      .catch((cause) => {
        if (!active) return;
        if (cause instanceof ApiError && cause.status === 401)
          window.location.reload();
        setLookupError(errorMessage(cause));
      });
    return () => {
      active = false;
    };
  }, [scan]);

  function reset() {
    last.current = "";
    setScan(null);
    setOrder(null);
    setLookupError("");
    op.setError("");
    input.current?.focus();
  }

  async function issue() {
    if (!order || !scan) return;
    const body = {
      target: "completed" as const,
      expected_version: order.version,
      pickup_code: scan.code,
    };
    const result: { order?: Order } = {};
    const ok = await op.run({ id: order.id, ...body }, async (key) => {
      result.order = await ordersApi.transition(order.id, body, key);
    });
    if (ok && result.order) {
      setDone(result.order);
      last.current = "";
      setScan(null);
      setOrder(null);
      input.current?.focus();
    }
  }

  return (
    <div className="scan-layout">
      <section className="scan-panel" aria-label="Сканирование QR-кода">
        <div className="scan-frame">
          {camera && !scan ? (
            <video
              ref={video}
              muted
              playsInline
              aria-label="Изображение с камеры"
            />
          ) : (
            <div className="scan-placeholder">
              <Icon name="qr" />
              <p>
                {scan
                  ? "Код считан"
                  : "Поднесите QR-код к сканеру или включите камеру"}
              </p>
            </div>
          )}
          <span className="scan-line" aria-hidden="true" />
        </div>
        {state === "denied" && camera && (
          <Alert title="Камера недоступна">
            Разрешите доступ к камере в браузере. Камера работает на localhost
            или по HTTPS. Ручной сканер работает всегда.
          </Alert>
        )}
        {state === "missing" && camera && (
          <Alert title="Камера недоступна">
            Браузер не поддерживает камеру. Используйте ручной сканер или
            введите данные вручную.
          </Alert>
        )}
        <div className="scan-controls">
          <Button
            variant={camera ? "secondary" : "primary"}
            icon="camera"
            onClick={() => setCamera((v) => !v)}
          >
            {camera ? "Выключить камеру" : "Включить камеру"}
          </Button>
          {(scan || lookupError || done) && (
            <Button variant="ghost" onClick={reset}>
              Следующий заказ
            </Button>
          )}
        </div>
        <form
          className="scan-manual"
          onSubmit={(e) => {
            e.preventDefault();
            last.current = "";
            accept(manual);
            setManual("");
          }}
        >
          <label htmlFor="scan-input">Ручной сканер или вставка данных</label>
          <input
            id="scan-input"
            ref={input}
            value={manual}
            onChange={(e) => setManual(e.target.value)}
            autoComplete="off"
            autoFocus
            placeholder="Отсканируйте QR-код ручным сканером"
          />
        </form>
      </section>

      <section className="scan-result" aria-live="polite">
        {done && (
          <div className="scan-success">
            <span className="success-badge" aria-hidden="true">
              <Icon name="check" />
            </span>
            <h2>Заказ №{orderNumber(done.id)} выдан</h2>
            <p>Порции списаны один раз. Можно сканировать следующий заказ.</p>
          </div>
        )}
        {lookupError && <Alert>{lookupError}</Alert>}
        {scan && !order && !lookupError && (
          <p className="muted">Загружаем заказ…</p>
        )}
        {order && (
          <article className="scan-order">
            <header>
              <h2>Заказ №{orderNumber(order.id)}</h2>
              <div className="badges">
                <Badge>{statuses[order.status]}</Badge>
                <Badge>
                  {order.dining === "takeaway" ? "С собой" : "В столовой"}
                </Badge>
              </div>
            </header>
            <p className="muted">
              Получение: {stockDate(order.slot_starts_at)} —{" "}
              {stockDate(order.slot_ends_at)}
            </p>
            <ul className="scan-lines">
              {order.lines.map((l) => (
                <li key={l.entry_id}>
                  <span>
                    {l.name}
                    <small>{l.portion_label}</small>
                  </span>
                  <strong>× {l.quantity}</strong>
                </li>
              ))}
            </ul>
            <p className="scan-total">
              Итого <strong>{stockMoney(order.total_minor)}</strong>
            </p>
            {order.stock_issue && (
              <Alert title="Требуется проверка">
                Партия из резерва приостановлена или просрочена. Не выдавайте
                заказ без управляющего.
              </Alert>
            )}
            {op.error && <Alert>{op.error}</Alert>}
            {order.status === "ready" && canIssue ? (
              <Button
                className="scan-issue"
                icon="check"
                loading={op.busy}
                disabled={order.stock_issue}
                onClick={() => void issue()}
              >
                Выдать заказ
              </Button>
            ) : order.status === "ready" ? (
              <p className="muted">
                Выдачу подтверждает кассир или управляющий.
              </p>
            ) : ["confirmed", "preparing"].includes(order.status) ? (
              <p className="muted">
                Заказ ещё не отмечен готовым. Соберите его в разделе «Заказы».
              </p>
            ) : null}
          </article>
        )}
      </section>
    </div>
  );
}
