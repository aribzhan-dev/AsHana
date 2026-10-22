import { useMemo } from "react";
import QRCode from "qrcode";

export function QrCode({
  value,
  label,
  size = 200,
}: {
  value: string;
  label: string;
  size?: number;
}) {
  const path = useMemo(() => {
    const { modules } = QRCode.create(value, { errorCorrectionLevel: "M" });
    const parts: string[] = [];
    for (let y = 0; y < modules.size; y++)
      for (let x = 0; x < modules.size; x++)
        if (modules.get(x, y)) parts.push(`M${x + 4} ${y + 4}h1v1h-1z`);
    return { d: parts.join(""), size: modules.size + 8 };
  }, [value]);
  return (
    <svg
      className="qr-code"
      role="img"
      aria-label={label}
      width={size}
      height={size}
      viewBox={`0 0 ${path.size} ${path.size}`}
      shapeRendering="crispEdges"
    >
      <rect width={path.size} height={path.size} fill="#ffffff" />
      <path d={path.d} fill="#111111" />
    </svg>
  );
}
