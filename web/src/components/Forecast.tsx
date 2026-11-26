import { useState } from "react";
import { buildForecastAction } from "../lib/actions";
import type { Action } from "../types";
import { Modal } from "./Modal";

export function ForecastModal({
  cards,
  legal,
  cityColor,
  onSubmit,
}: {
  cards: string[];
  legal: Action[];
  cityColor: (c: string) => string | undefined;
  onSubmit: (a: Action) => void;
}) {
  const [order, setOrder] = useState(cards);
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const move = (i: number, j: number) => {
    if (j < 0 || j >= order.length || i === j) return;
    const o = [...order];
    const [c] = o.splice(i, 1);
    o.splice(j, 0, c);
    setOrder(o);
  };
  const action = buildForecastAction(order, legal);
  return (
    <Modal title="Forecast: arrange the infection deck">
      <p className="muted">
        The top card is drawn first. Drag cards or use the arrows, then submit.
      </p>
      <ol className="forecast">
        {order.map((c, i) => (
          <li
            key={c}
            draggable
            className={"fc " + (cityColor(c) ?? "")}
            onDragStart={() => setDragFrom(i)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => {
              if (dragFrom !== null) move(dragFrom, i);
              setDragFrom(null);
            }}
          >
            <span className="fc-pos">{i === 0 ? "TOP" : i + 1}</span>
            <span className="grow">{c}</span>
            <button onClick={() => move(i, i - 1)} disabled={i === 0} aria-label="Move up">
              ↑
            </button>
            <button onClick={() => move(i, i + 1)} disabled={i === order.length - 1} aria-label="Move down">
              ↓
            </button>
          </li>
        ))}
      </ol>
      <div className="row">
        <button className="primary" disabled={!action} onClick={() => action && onSubmit(action)}>
          Submit order
        </button>
        <button onClick={() => setOrder(cards)}>Reset</button>
      </div>
      {!action && <p className="muted">That order is not offered by the server.</p>}
    </Modal>
  );
}
