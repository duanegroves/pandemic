import { type FormEvent, type ReactNode, useState } from "react";
import { type LogEntry, type LogSection, groupLog } from "../lib/eventLog";
import { DISEASE_FILL } from "../lib/theme";
import type { ChatMsg, Color } from "../types";

/** Player colour for a seat (their pawn colour), when known. */
export type ColorOf = (seat: number) => string | undefined;

function Cube({ color }: { color: Color }) {
  return <span className="log-cube" style={{ background: DISEASE_FILL[color] }} aria-label={color} />;
}

/**
 * The game log, grouped by turn, newest turn at the top (lines within a turn stay in the order they
 * happened). Each turn starts with a catch-up summary (cards drawn, cities infected, epidemics,
 * outbreaks); the two most recent turns are expanded, older ones fold away. Lines are coloured by who did them (the player's pawn colour)
 * or, for things the board did, by the disease involved; epidemics/outbreaks and cures stand out.
 */
export function EventLog({
  log,
  name,
  colorOf,
}: {
  log: LogEntry[];
  name: (seat: number) => string;
  colorOf?: ColorOf;
}) {
  const sections = groupLog(log).reverse();
  return (
    <div className="log turnlog">
      {sections.length === 0 && <div className="muted">Nothing yet.</div>}
      {sections.map((s, i) => (
        <Section key={s.key} s={s} open={i < 2} name={name} colorOf={colorOf} />
      ))}
    </div>
  );
}

function Section({
  s,
  open,
  name,
  colorOf,
}: {
  s: LogSection;
  open: boolean;
  name: (seat: number) => string;
  colorOf?: ColorOf;
}) {
  const color = s.turn ? colorOf?.(s.turn.player) : undefined;
  const title = s.turn ? `Turn ${s.turn.n} · ${name(s.turn.player)}` : "Setup";
  const shown = s.entries.filter((e) => !e.quiet);
  return (
    <details className="turn" open={open}>
      <summary className="turn-head" style={color ? { borderLeftColor: color } : undefined}>
        <span className="turn-title">{title}</span>
        <Summary s={s} name={name} />
      </summary>
      <ul className="turn-lines">
        {shown.map((e) => (
          <Line key={e.id} e={e} colorOf={colorOf} />
        ))}
      </ul>
    </details>
  );
}

/** One line of chips answering: what was drawn, what got infected, any epidemic or outbreak. */
function Summary({ s, name }: { s: LogSection; name: (seat: number) => string }) {
  const { drew, infected, epidemics, outbreaks, cures, gameOver } = s.summary;
  const chips: ReactNode[] = [];
  for (const d of drew)
    if (d.cards.length)
      chips.push(
        <span key={"d" + d.player} className="chip">
          {name(d.player)} drew{" "}
          {d.cards.every((c) => c === "a card")
            ? `${d.cards.length} card${d.cards.length === 1 ? "" : "s"}` // hidden hands
            : d.cards.join(", ")}
        </span>,
      );
  if (infected.length)
    chips.push(
      <span key="inf" className="chip">
        Infected:{" "}
        {infected.map((x, i) => (
          <span key={x.city + x.color} className="inf">
            {i > 0 && ", "}
            <Cube color={x.color} />
            {x.city} +{x.count}
          </span>
        ))}
      </span>,
    );
  for (const c of epidemics)
    chips.push(
      <span key={"e" + c} className="chip alert">
        ⚠ Epidemic: {c}
      </span>,
    );
  if (outbreaks.length)
    chips.push(
      <span key="o" className="chip alert">
        ⚠ Outbreak{outbreaks.length > 1 ? "s" : ""}:{" "}
        {outbreaks.map((o, i) => (
          <span key={o.city + i}>
            {i > 0 && ", "}
            <Cube color={o.color} />
            {o.city}
          </span>
        ))}
      </span>,
    );
  for (const c of cures)
    chips.push(
      <span key={"c" + c} className="chip milestone">
        ✓ <Cube color={c} />
        {c} cured
      </span>,
    );
  if (gameOver)
    chips.push(
      <span key="go" className={"chip " + (gameOver.win ? "milestone" : "alert")}>
        {gameOver.win ? "✓ Victory" : "⚠ Defeat"}
      </span>,
    );
  if (!chips.length) return null;
  return <span className="turn-summary">{chips}</span>;
}

function Line({ e, colorOf }: { e: LogEntry; colorOf?: ColorOf }) {
  const bar = e.actor != null ? colorOf?.(e.actor) : undefined;
  const cls = "line" + (e.emphasis ? " " + e.emphasis : "") + (e.actor == null ? " board" : "");
  return (
    <li className={cls} style={bar ? { borderLeftColor: bar } : undefined}>
      {e.emphasis === "alert" && "⚠ "}
      {e.emphasis === "milestone" && "✓ "}
      {e.actor == null && e.disease && <Cube color={e.disease} />}
      {e.text}
    </li>
  );
}

/**
 * Chat with the input on top and the newest message right below it, so your eye barely moves
 * after sending. `colorOf(seat)` gives the speaker's player colour for the bar beside each message.
 */
export function ChatBox({
  chat,
  send,
  colorOf,
}: {
  chat: ChatMsg[];
  send: (m: object) => boolean;
  colorOf?: ColorOf;
}) {
  const [text, setText] = useState("");

  const submit = (ev: FormEvent) => {
    ev.preventDefault();
    if (!text.trim()) return;
    if (send({ type: "chat", text })) setText("");
  };
  return (
    <div className="chat">
      <form className="row" onSubmit={submit}>
        <input className="grow" value={text} onChange={(e) => setText(e.target.value)} placeholder="Say something..." />
        <button>Send</button>
      </form>
      <ul className="log chatlog">
        {chat.length === 0 && <li className="muted">No messages.</li>}
        {[...chat].reverse().map((m, i) => {
          const color = colorOf?.(m.seat);
          return (
            <li key={chat.length - i} style={color ? { borderLeftColor: color } : undefined}>
              <strong>{m.name}:</strong> {m.text}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
