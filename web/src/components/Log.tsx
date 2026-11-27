import { type FormEvent, useState } from "react";
import type { LogEntry } from "../lib/eventLog";
import type { ChatMsg } from "../types";

export function EventLog({ log }: { log: LogEntry[] }) {
  const rev = [...log].reverse();
  return (
    <ul className="log">
      {rev.length === 0 && <li className="muted">Nothing yet.</li>}
      {rev.map((e) => (
        <li key={e.id} className={"tone-" + e.tone}>
          {e.text}
        </li>
      ))}
    </ul>
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
  colorOf?: (seat: number) => string | undefined;
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
