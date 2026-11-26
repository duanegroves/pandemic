import { useState } from "react";
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
  onPick: (a: Action) => void;
  onClose: () => void;
}

/** Step through the parameters of several candidate actions until exactly one remains. */
export function Chooser({ title, actions, keys, label, prompt, onPick, onClose }: Props) {
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const r = narrow(actions, keys, chosen);
  if ("done" in r) {
    return (
      <Modal title={title} onClose={onClose}>
        <p>
          {Object.entries(chosen).map(([k, id]) => (
            <span key={k} className="chip">
              {label(k, JSON.parse(id))}
            </span>
          ))}
        </p>
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
        <p>No matching options.</p>
        <button onClick={() => setChosen({})}>Start over</button>
      </Modal>
    );
  }
  const { key, options } = r.choice;
  return (
    <Modal title={title} onClose={onClose}>
      <p className="muted">{prompt?.[key] ?? `Choose ${key.replace(/_/g, " ")}`}</p>
      <div className="options">
        {options.map((o) => (
          <button key={o.id} onClick={() => setChosen({ ...chosen, [key]: o.id })}>
            {label(key, o.value)}
          </button>
        ))}
      </div>
      <div className="row">
        {Object.keys(chosen).length > 0 && <button onClick={() => setChosen({})}>Back</button>}
        <button onClick={onClose}>Cancel</button>
      </div>
    </Modal>
  );
}
