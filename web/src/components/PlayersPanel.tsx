import { useState } from "react";
import { ROLE_LABEL } from "../lib/actions";
import { eventInfo } from "../lib/eventCards";
import { ROLE_INFO } from "../lib/roles";
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
  /** Show what an Event card does (cards you can't play right now, or another player's). */
  onEventInfo: (card: string, holder: number) => void;
  onLocate: (city: string) => void;
}

export function PlayersPanel({
  obs,
  names,
  you,
  playable,
  selected,
  selectable,
  onCard,
  onEventInfo,
  onLocate,
}: Props) {
  const cities = useCityMap();
  const meta = useMeta();
  const owner = obs.decision.player;
  // Which players' role descriptions are expanded: your own starts open.
  const [openRoles, setOpenRoles] = useState<Set<number>>(() => new Set([you]));
  const toggle = (set: typeof setOpenRoles) => (i: number) =>
    set((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  const toggleRole = toggle(setOpenRoles);

  const card = (c: string, from: "hand" | "stored", key: string | number, own: boolean, holder: number) => {
    const isEvent = meta.events.includes(c);
    const color = cities.get(c)?.color;
    // Your own card that does something when clicked right now (select to discard, or play).
    const acts = own && (c === selected || (isEvent && playable.has(c)) || (selectable && from === "hand"));
    // Event cards can always be clicked to see what they do.
    const clickable = acts || isEvent;
    return (
      <button
        key={key}
        className={
          "card-chip " + (isEvent ? "event" : (color ?? "")) + (selected === c ? " selected" : "") + (clickable ? " clickable" : "")
        }
        disabled={!clickable}
        title={isEvent ? `${c}: ${eventInfo(c) ?? "Event card"}` : (cities.get(c)?.color ?? "")}
        onClick={() => (acts ? onCard(c, from) : onEventInfo(c, holder))}
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
              <button
                className="role-toggle"
                aria-expanded={openRoles.has(p.index)}
                title={openRoles.has(p.index) ? "Hide what this role does" : "What does this role do?"}
                onClick={() => toggleRole(p.index)}
              >
                {ROLE_LABEL[p.role] ?? p.role} <span className="role-i">ⓘ</span>
              </button>{" "}
              in{" "}
              <button className="link" onClick={() => onLocate(p.location)}>
                {p.location}
              </button>
            </div>
            {openRoles.has(p.index) && ROLE_INFO[p.role] && (
              <div className="role-info" style={{ borderLeftColor: st?.fill }}>
                <div className="role-summary">{ROLE_INFO[p.role].summary}</div>
                <ul>
                  {ROLE_INFO[p.role].abilities.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="hand">
              {p.hand ? (
                p.hand.length ? (
                  p.hand.map((c, i) => card(c, "hand", i, mine, p.index))
                ) : (
                  <span className="muted">empty hand</span>
                )
              ) : (
                <span className="muted">{p.hand_size} cards (hidden)</span>
              )}
            </div>
            {p.stored_event && (
              <div className="hand">
                <span className="muted">Stored:</span> {card(p.stored_event, "stored", "s", mine, p.index)}
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}
