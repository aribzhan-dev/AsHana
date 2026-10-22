import { useRef, useState } from "react";
import { useLiveReload } from "../../shared/lib/live-events";
import { orderNumber } from "../../shared/lib/pickup-qr";
import { Button } from "../../shared/ui/Button";
import { LiveBadge } from "../../shared/ui/LiveBadge";
import { Icon } from "../../shared/ui/Icon";

const SOUND_KEY = "ashana-kitchen-sound";

function readSound(): boolean {
  try {
    return localStorage.getItem(SOUND_KEY) === "on";
  } catch {
    return false;
  }
}

// Browsers allow audio only after a click, so the context is created by the toggle.
function chime(context: AudioContext) {
  for (const [delay, frequency] of [
    [0, 880],
    [0.18, 1175],
  ] as const) {
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0.2, context.currentTime + delay);
    gain.gain.exponentialRampToValueAtTime(
      0.001,
      context.currentTime + delay + 0.25,
    );
    oscillator.connect(gain).connect(context.destination);
    oscillator.start(context.currentTime + delay);
    oscillator.stop(context.currentTime + delay + 0.3);
  }
}

export function KitchenLive({ onReload }: { onReload: () => void }) {
  const [sound, setSound] = useState(readSound),
    [incoming, setIncoming] = useState<string[]>([]);
  const audio = useRef<AudioContext | null>(null);
  const live = useLiveReload(["orders"], onReload, (event) => {
    if (event.kind !== "confirmed" || !event.id) return;
    setIncoming((list) =>
      [`Новый заказ №${orderNumber(event.id)}`, ...list].slice(0, 3),
    );
    if (sound && audio.current) chime(audio.current);
  });
  function toggle() {
    const next = !sound;
    setSound(next);
    if (next) {
      audio.current ??= new AudioContext();
      void audio.current.resume();
      chime(audio.current);
    }
    try {
      localStorage.setItem(SOUND_KEY, next ? "on" : "off");
    } catch {
      // Without storage the choice lasts for this page only.
    }
  }
  return (
    <div className="kitchen-live">
      <div className="live-row">
        <LiveBadge status={live} />
        <Button
          variant="secondary"
          icon="bell"
          aria-pressed={sound}
          onClick={toggle}
        >
          {sound ? "Звук включён" : "Включить звук"}
        </Button>
      </div>
      {incoming.length > 0 && (
        <div className="incoming" role="alert">
          <Icon name="bell" />
          <div>
            {incoming.map((text, index) => (
              <strong key={`${text}-${index}`}>{text}</strong>
            ))}
          </div>
          <Button variant="ghost" onClick={() => setIncoming([])}>
            Понятно
          </Button>
        </div>
      )}
    </div>
  );
}
