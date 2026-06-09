import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * STANDARD feature-screen layout primitive (IMPLEMENTATION_GUIDE §2.6 / policy.md).
 *
 * A vertical split whose BOTTOM pane (the managing AI worker chat area) is resizable
 * by dragging the divider. Generated feature screens use this so that
 * "the worker chat area is drag-resizable" is a STANDARD affordance provided by the
 * component — the UI Designer agent just declares the standard layout and never
 * hand-codes drag logic. The chosen height is persisted per user (localStorage).
 */
export function ResizableSplit({
  top,
  bottom,
  storageKey,
  min = 120,
  max = 640,
  initialBottom = 220,
}: {
  top: ReactNode;
  bottom: ReactNode;
  storageKey?: string;
  min?: number;
  max?: number;
  initialBottom?: number;
}) {
  const clamp = (v: number) => Math.max(min, Math.min(max, v));

  const [height, setHeightState] = useState(() => {
    if (storageKey) {
      const saved = Number(localStorage.getItem(storageKey));
      if (Number.isFinite(saved) && saved >= min && saved <= max) return saved;
    }
    return clamp(initialBottom);
  });
  const hRef = useRef(height);
  const drag = useRef<{ startY: number; startH: number } | null>(null);

  function setHeight(v: number) {
    const c = clamp(v);
    hRef.current = c;
    setHeightState(c);
  }

  function onPointerDown(e: React.PointerEvent) {
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    drag.current = { startY: e.clientY, startH: hRef.current };
  }
  function onPointerMove(e: React.PointerEvent) {
    if (!drag.current) return;
    // Dragging up (smaller clientY) grows the bottom pane.
    setHeight(drag.current.startH + (drag.current.startY - e.clientY));
  }
  function onPointerUp(e: React.PointerEvent) {
    if (!drag.current) return;
    (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    drag.current = null;
    if (storageKey) localStorage.setItem(storageKey, String(hRef.current));
  }

  // Keep within bounds if min/max props change.
  useEffect(() => { setHeight(hRef.current); }, [min, max]); // eslint-disable-line

  return (
    <div className="rsplit">
      <div className="rsplit__top">{top}</div>
      <div
        className="rsplit__handle"
        role="separator"
        aria-orientation="horizontal"
        aria-label="会話エリアの高さを変更"
        title="ドラッグで会話エリアの高さを変更"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      />
      <div className="rsplit__bottom" style={{ height }}>{bottom}</div>
    </div>
  );
}
