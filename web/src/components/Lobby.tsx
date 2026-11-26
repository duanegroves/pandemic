import { useState } from "react";
import type { RoomView } from "../useRoomSocket";
import { ChatBox } from "./Log";

interface Props {
  roomId: string;
  view: RoomView;
  send: (m: object) => boolean;
  onLeave: () => void;
}

export function Lobby({ roomId, view, send, onLeave }: Props) {
  const lobby = view.lobby;
  const [copied, setCopied] = useState(false);
  const link = `${location.origin}${location.pathname}?room=${roomId}`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      window.prompt("Copy this link", link);
    }
  };
  if (!lobby) return <div className="center-msg">Waiting for lobby...</div>;
  const me = lobby.seats.find((s) => s.seat === lobby.you);
  const full = lobby.seats.length === lobby.capacity;
  const allReady = lobby.seats.every((s) => s.ready);
  const cfg = lobby.config as Record<string, unknown>;
  return (
    <div className="home">
      <h1>Lobby</h1>
      <div className="card">
        <div className="row">
          <div>
            Room code <strong className="code">{roomId}</strong>
          </div>
          <input className="grow" readOnly value={link} onFocus={(e) => e.target.select()} />
          <button onClick={copy}>{copied ? "Copied" : "Copy link"}</button>
        </div>
        <p className="muted">
          {lobby.capacity} players, {String(cfg.difficulty ?? "standard")}, event windows:{" "}
          {String(cfg.event_windows ?? "checkpoints")}, hands:{" "}
          {cfg.open_hands == null ? "per rulebook" : cfg.open_hands ? "open" : "hidden"}
          {cfg.auto_consent === false ? ", consent required" : ""}
          {lobby.timeout ? `, ${lobby.timeout}s timeout` : ""}
        </p>
        <ul className="seats">
          {Array.from({ length: lobby.capacity }, (_, i) => {
            const s = lobby.seats.find((x) => x.seat === i);
            if (!s)
              return (
                <li key={i} className="seat empty">
                  Waiting for player...
                </li>
              );
            return (
              <li key={i} className={"seat" + (s.seat === lobby.you ? " me" : "")}>
                <span className={"dot " + (s.connected ? "on" : "off")} title={s.connected ? "connected" : "disconnected"} />
                <span className="grow">
                  {s.name}
                  {s.seat === lobby.you ? " (you)" : ""}
                </span>
                {s.host && <span className="tag">host</span>}
                <span className={"tag " + (s.ready ? "ok" : "")}>{s.ready ? "ready" : "not ready"}</span>
              </li>
            );
          })}
        </ul>
        <div className="row">
          <button className="primary" onClick={() => send({ type: "ready", ready: !me?.ready })}>
            {me?.ready ? "Not ready" : "Ready"}
          </button>
          {me?.host && (
            <button
              className="primary"
              disabled={!full || !allReady}
              title={!full ? "Waiting for all players" : !allReady ? "Everyone must be ready" : ""}
              onClick={() => send({ type: "start" })}
            >
              Start game
            </button>
          )}
          <button onClick={onLeave}>Leave</button>
        </div>
      </div>
      <ChatBox chat={view.chat} send={send} />
    </div>
  );
}
