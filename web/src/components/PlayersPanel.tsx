import { ROLE_LABEL } from "../lib/actions";
import { ROLE_STYLE } from "../lib/theme";
import { useCityMap, useMeta } from "../meta";
import type { Observation } from "../types";

interface Props {
  obs: Observation;
  names: string[];
  you: number;
  /** Event cards that currently have legal plays. */
  playable: Set<string>;
  selected: string | null;
  selectable: boolean;
  onCard: (card: string, from: "hand" | "stored") => void;
  onLocate: (city: string) => void;
}

export function PlayersPanel({ obs, names, you, playable, selected, selectable, onCard, onLocate }: Props) {
  const cities = useCityMap();
  const meta = useMeta();
  const owner = obs.decision.player;

  const card = (c: string, from: "hand" | "stored", key: string | number, own: boolean) => {
    const isEvent = meta.events.includes(c);
    const color = cities.get(c)?.color;
    const clickable = own && (c === selected || (isEvent && playable.has(c)) || (selectable && from === "hand"));
    return (
      <button
        key={key}
        className={
          "card-chip " + (isEvent ? "event" : (color ?? "")) + (selected === c ? " selected" : "") + (clickable ? " clickable" : "")
        }
        disabled={!clickable}
        title={isEvent ? (playable.has(c) ? "Click to play" : "Event card") : (cities.get(c)?.color ?? "")}
        onClick={() => onCard(c, from)}
      >
        {c}
      </button>
    );
  };

  return (
    <section className="panel players">
      <h3>Players</h3>
      {obs.players.map((p) => {
        const st = ROLE_STYLE[p.role];
        const turn = p.index === obs.current_player;
        const mine = p.index === you;
        return (
          <div key={p.index} className={"player" + (turn ? " turn" : "") + (mine ? " me" : "")}>
            <div className="player-head">
              <span className="pawn-dot" style={{ background: st?.fill, color: st?.text }}>
                {st?.initials}
              </span>
              <b>{names[p.index] ?? `Player ${p.index + 1}`}</b>
              {mine && <span className="tag">you</span>}
              {turn && <span className="tag ok">turn</span>}
              {owner === p.index && <span className="tag warn">deciding: {obs.decision.kind.replace(/_/g, " ")}</span>}
            </div>
            <div className="muted">
              {ROLE_LABEL[p.role] ?? p.role} in{" "}
              <button className="link" onClick={() => onLocate(p.location)}>
                {p.location}
              </button>
            </div>
            <div className="hand">
              {p.hand ? (
                p.hand.length ? (
                  p.hand.map((c, i) => card(c, "hand", i, mine))
                ) : (
                  <span className="muted">empty hand</span>
                )
              ) : (
                <span className="muted">{p.hand_size} cards (hidden)</span>
              )}
            </div>
            {p.stored_event && (
              <div className="hand">
                <span className="muted">Stored:</span> {card(p.stored_event, "stored", "s", mine)}
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}
