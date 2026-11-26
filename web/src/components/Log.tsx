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

export function ChatBox({ chat, send }: { chat: ChatMsg[]; send: (m: object) => boolean }) {
  const [text, setText] = useState("");
  const submit = (ev: FormEvent) => {
    ev.preventDefault();
    if (!text.trim()) return;
    if (send({ type: "chat", text })) setText("");
  };
  return (
    <div className="chat">
      <ul className="log chatlog">
        {chat.length === 0 && <li className="muted">No messages.</li>}
        {[...chat].reverse().map((m, i) => (
          <li key={chat.length - i}>
            <strong>{m.name}:</strong> {m.text}
          </li>
        ))}
      </ul>
      <form className="row" onSubmit={submit}>
        <input className="grow" value={text} onChange={(e) => setText(e.target.value)} placeholder="Say something..." />
        <button>Send</button>
      </form>
    </div>
  );
}
