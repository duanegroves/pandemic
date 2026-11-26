import type { Meta } from "../types";

export interface Session {
  seat: number;
  token: string;
  name: string;
}

const key = (room: string) => `pandemic:session:${room}`;

export function loadSession(room: string): Session | null {
  try {
    const raw = sessionStorage.getItem(key(room));
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function saveSession(room: string, s: Session): void {
  try {
    sessionStorage.setItem(key(room), JSON.stringify(s));
  } catch {
    /* storage unavailable: session lives only in memory */
  }
}

export function clearSession(room: string): void {
  try {
    sessionStorage.removeItem(key(room));
  } catch {
    /* ignore */
  }
}

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const b = await r.json();
      msg = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail ?? b);
    } catch {
      /* not json */
    }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export interface CreateParams {
  config: Record<string, unknown>;
  timeout: number | null;
  timeout_consent: boolean;
}

export const createRoom = (p: CreateParams) =>
  fetch("/rooms", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(p),
  }).then((r) => j<{ room_id: string }>(r));

export const joinRoom = (room: string, name: string, token: string | null) =>
  fetch(`/rooms/${encodeURIComponent(room)}/join`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name, token }),
  }).then((r) => j<{ room_id: string; seat: number; token: string }>(r));

export const getRoom = (room: string) =>
  fetch(`/rooms/${encodeURIComponent(room)}`).then((r) => j<{ phase: string }>(r));

export const getMeta = () => fetch("/meta").then((r) => j<Meta>(r));

export function wsUrl(room: string, token: string): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/${encodeURIComponent(room)}?token=${encodeURIComponent(token)}`;
}
