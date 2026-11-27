import { useState } from "react";
import { ROLE_LABEL } from "../lib/actions";
import { EVENT_RULES, eventInfo } from "../lib/eventCards";
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
  onLocate: (city: string) => void;
}

export function PlayersPanel({ obs, names, you, playable, selected, selectable, onCard, onLocate }: Props) {
  const cities = useCityMap();
  const meta = useMeta();
  const owner = obs.decision.player;
  // Which players' role descriptions are expanded: your own starts open.
  const [openRoles, setOpenRoles] = useState<Set<number>>(() => new Set([you]));
  // Which players' event card descriptions are expanded (all start closed).
  const [openEvents, setOpenEvents] = useState<Set<number>>(() => new Set());
  const toggle = (set: typeof setOpenRoles) => (i: number) =>
    set((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  const toggleEvents = toggle(setOpenEvents);
  const toggleRole = toggle(setOpenRoles);

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
        title={
          isEvent
            ? `${c}: ${eventInfo(c) ?? "Event card"}${playable.has(c) && own ? " (click to play)" : ""}`
            : (cities.get(c)?.color ?? "")
        }
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
            {(() => {
              const events = [...(p.hand ?? []), ...(p.stored_event ? [p.stored_event] : [])].filter(
                (c, i, all) => eventInfo(c) && all.indexOf(c) === i,
              );
              if (!events.length) return null;
              const open = openEvents.has(p.index);
              return (
                <>
                  <button
                    className="role-toggle events-toggle"
                    aria-expanded={open}
                    onClick={() => toggleEvents(p.index)}
                  >
                    <span className="role-i">ⓘ</span>{" "}
                    {open
                      ? `Hide event card${events.length === 1 ? "" : "s"}`
                      : events.length === 1
                        ? "What does this event card do?"
                        : "What do these event cards do?"}
                  </button>
                  {open && (
                    <div className="role-info event-info">
                      {events.map((c) => (
                        <div key={c} className="event-desc">
                          <b>{c}:</b> {eventInfo(c)}
                        </div>
                      ))}
                      <div className="event-rules">{EVENT_RULES}</div>
                    </div>
                  )}
                </>
              );
            })()}
          </div>
        );
      })}
    </section>
  );
}
