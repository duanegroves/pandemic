import { type ReactNode, useState } from "react";
import { narrow } from "../lib/actions";
import type { Action } from "../types";
import { Modal } from "./Modal";

interface Props {
  title: string;
  actions: Action[];
  keys: string[];
  /** Label for an option value of a parameter key. */
  label: (key: string, value: unknown) => string;
  prompt?: Record<string, string>;
  /** Shown at the top of every step (e.g. what the Event card being played does). */
  intro?: ReactNode;
  /** Optional one-line explanation of an option (e.g. what an Event card does), shown under it. */
  describe?: (key: string, value: unknown) => string | undefined;
  onPick: (a: Action) => void;
  onClose: () => void;
}

/** Step through the parameters of several candidate actions until exactly one remains. */
export function Chooser({ title, actions, keys, label, prompt, intro, describe, onPick, onClose }: Props) {
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const r = narrow(actions, keys, chosen);
  if ("done" in r) {
    return (
      <Modal title={title} onClose={onClose}>
        {intro}
        <p>
          {Object.entries(chosen).map(([k, id]) => (
            <span key={k} className="chip">
              {label(k, JSON.parse(id))}
            </span>
          ))}
        </p>
        {Object.entries(chosen).map(([k, id]) => {
          const d = describe?.(k, JSON.parse(id));
          return d ? (
            <p key={k} className="option-desc">
              {d}
            </p>
          ) : null;
        })}
        <div className="row">
          <button className="primary" onClick={() => onPick(r.done)}>
            Confirm
          </button>
          {Object.keys(chosen).length > 0 && <button onClick={() => setChosen({})}>Start over</button>}
          <button onClick={onClose}>Cancel</button>
        </div>
      </Modal>
    );
  }
  if ("none" in r) {
    return (
      <Modal title={title} onClose={onClose}>
        {intro}
        <p>No matching options.</p>
        <button onClick={() => setChosen({})}>Start over</button>
      </Modal>
    );
  }
  const { key, options } = r.choice;
  return (
    <Modal title={title} onClose={onClose}>
      {intro}
      <p className="muted">{prompt?.[key] ?? `Choose ${key.replace(/_/g, " ")}`}</p>
      <div className="options">
        {options.map((o) => {
          const d = describe?.(key, o.value);
          return (
            <button
              key={o.id}
              className={d ? "described" : undefined}
              onClick={() => setChosen({ ...chosen, [key]: o.id })}
            >
              {d ? <b>{label(key, o.value)}</b> : label(key, o.value)}
              {d && <span className="option-desc">{d}</span>}
            </button>
          );
        })}
      </div>
      <div className="row">
        {Object.keys(chosen).length > 0 && <button onClick={() => setChosen({})}>Back</button>}
        <button onClick={onClose}>Cancel</button>
      </div>
    </Modal>
  );
}
