import { useCallback, useEffect, useReducer, useRef } from "react";
import { backoffMs } from "./lib/countdown";
import { type LogEntry, formatEvents } from "./lib/eventLog";
import { wsUrl } from "./lib/net";
import type { Action, ChatMsg, LobbyMsg, StateMsg } from "./types";

export type Status = "connecting" | "open" | "reconnecting" | "denied";

export interface RoomView {
  status: Status;
  lobby: LobbyMsg | null;
  game: { msg: StateMsg; receivedAt: number } | null;
  log: LogEntry[]; // chronological
  chat: ChatMsg[];
  error: { text: string; n: number } | null;
}

type Ev =
  | { t: "status"; status: Status }
  | { t: "lobby"; msg: LobbyMsg }
  | { t: "state"; msg: StateMsg; entries: LogEntry[] }
  | { t: "chat"; msg: ChatMsg }
  | { t: "error"; text: string }
  | { t: "clearError" };

const MAX_LOG = 400;

function reduce(s: RoomView, e: Ev): RoomView {
  switch (e.t) {
    case "status":
      return { ...s, status: e.status };
    case "lobby":
      return { ...s, lobby: e.msg };
    case "state":
      return {
        ...s,
        game: { msg: e.msg, receivedAt: Date.now() },
        log: e.entries.length ? [...s.log, ...e.entries].slice(-MAX_LOG) : s.log,
      };
    case "chat":
      return { ...s, chat: [...s.chat.slice(-199), e.msg] };
    case "error":
      return { ...s, error: { text: e.text, n: (s.error?.n ?? 0) + 1 } };
    case "clearError":
      return { ...s, error: null };
  }
}

const logKey = (room: string) => `pandemic:log:${room}`;

function loadLog(room: string): LogEntry[] {
  try {
    return JSON.parse(sessionStorage.getItem(logKey(room)) ?? "[]");
  } catch {
    return [];
  }
}

/**
 * WebSocket connection to a room with automatic reconnect (exponential backoff). The server resends the
 * current lobby/state message on every connect, so reconnecting needs no extra handshake.
 */
export function useRoomSocket(roomId: string, token: string, onDenied: () => void) {
  const [view, dispatch] = useReducer(reduce, undefined, () => ({
    status: "connecting" as Status,
    lobby: null,
    game: null,
    log: loadLog(roomId),
    chat: [],
    error: null,
  }));
  const wsRef = useRef<WebSocket | null>(null);
  const namesRef = useRef<string[]>([]);
  const youRef = useRef<number | null>(null);
  const nextId = useRef(Date.now());
  const deniedRef = useRef(onDenied);
  deniedRef.current = onDenied;

  useEffect(() => {
    let closed = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const ws = new WebSocket(wsUrl(roomId, token));
      wsRef.current = ws;
      ws.onopen = () => {
        attempt = 0;
        dispatch({ t: "status", status: "open" });
      };
      ws.onmessage = (ev) => {
        let m: { type: string };
        try {
          m = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (m.type === "lobby") {
          const l = m as LobbyMsg;
          namesRef.current = l.seats.map((x) => x.name);
          youRef.current = l.you;
          dispatch({ t: "lobby", msg: l });
        } else if (m.type === "state") {
          const st = m as StateMsg;
          youRef.current = st.you;
          const entries = formatEvents(
            st.events,
            { name: (i) => namesRef.current[i] ?? `Player ${i + 1}`, you: st.you },
            nextId.current,
          );
          nextId.current += entries.length;
          dispatch({ t: "state", msg: st, entries });
        } else if (m.type === "chat") {
          dispatch({ t: "chat", msg: m as ChatMsg });
        } else if (m.type === "error") {
          const er = m as unknown as { message: string };
          dispatch({ t: "error", text: er.message });
        }
      };
      ws.onclose = (ev) => {
        if (closed) return;
        if (ev.code === 4401) {
          dispatch({ t: "status", status: "denied" });
          deniedRef.current();
          return;
        }
        dispatch({ t: "status", status: "reconnecting" });
        timer = setTimeout(connect, backoffMs(attempt++));
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      wsRef.current?.close();
    };
  }, [roomId, token]);

  // persist the log per tab so it survives a reload
  useEffect(() => {
    try {
      sessionStorage.setItem(logKey(roomId), JSON.stringify(view.log.slice(-200)));
    } catch {
      /* ignore */
    }
  }, [roomId, view.log]);

  // auto-dismiss errors
  useEffect(() => {
    if (!view.error) return;
    const t = setTimeout(() => dispatch({ t: "clearError" }), 5000);
    return () => clearTimeout(t);
  }, [view.error]);

  const send = useCallback((msg: object) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
      return true;
    }
    dispatch({ t: "error", text: "Not connected; retrying..." });
    return false;
  }, []);

  const sendAction = useCallback((action: Action) => send({ type: "action", action }), [send]);

  return { view, send, sendAction };
}
