import { type FormEvent, useState } from "react";
import { type Session, createRoom, joinRoom, loadSession, saveSession } from "../lib/net";

const NAME_KEY = "pandemic:name";
const getName = () => {
  try {
    return localStorage.getItem(NAME_KEY) ?? "";
  } catch {
    return "";
  }
};
const setName = (n: string) => {
  try {
    localStorage.setItem(NAME_KEY, n);
  } catch {
    /* ignore */
  }
};

type Enter = (room: string, s: Session) => void;

async function joinAndEnter(room: string, name: string, onEnter: Enter) {
  const prev = loadSession(room);
  const r = await joinRoom(room, name, prev?.token ?? null);
  const s = { seat: r.seat, token: r.token, name };
  saveSession(room, s);
  setName(name);
  onEnter(room, s);
}

export function Home({ onEnter }: { onEnter: Enter }) {
  const [name, setNm] = useState(getName);
  const [players, setPlayers] = useState(2);
  const [difficulty, setDifficulty] = useState("introductory");
  const [openHands, setOpenHands] = useState<"default" | "open" | "closed">("default");
  const [windows, setWindows] = useState("checkpoints");
  const [consent, setConsent] = useState(false);
  const [timeout, setTimeoutS] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const create = (ev: FormEvent) => {
    ev.preventDefault();
    run(async () => {
      const config: Record<string, unknown> = {
        num_players: players,
        difficulty,
        event_windows: windows,
        auto_consent: !consent,
      };
      if (openHands !== "default") config.open_hands = openHands === "open";
      const t = parseFloat(timeout);
      const { room_id } = await createRoom({
        config,
        timeout: t > 0 ? t : null,
        timeout_consent: t > 0,
      });
      await joinAndEnter(room_id, name.trim() || "Host", onEnter);
    });
  };

  const join = (ev: FormEvent) => {
    ev.preventDefault();
    run(() => joinAndEnter(code.trim(), name.trim() || "Player", onEnter));
  };

  return (
    <div className="home">
      <h1>Pandemic</h1>
      <p className="muted">Cooperative disease-fighting for 2 to 4 players.</p>
      <label className="field">
        Your name
        <input value={name} onChange={(e) => setNm(e.target.value)} maxLength={20} placeholder="Name" />
      </label>
      {err && <div className="banner bad">{err}</div>}
      <div className="home-cols">
        <form className="card" onSubmit={create}>
          <h2>Create a room</h2>
          <label className="field">
            Players
            <select value={players} onChange={(e) => setPlayers(+e.target.value)}>
              {[2, 3, 4].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
          <label className="field">
            Difficulty
            <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              <option value="introductory">Introductory (4 epidemics)</option>
              <option value="standard">Standard (5 epidemics)</option>
              <option value="heroic">Heroic (6 epidemics)</option>
            </select>
          </label>
          <label className="field">
            Hands
            <select value={openHands} onChange={(e) => setOpenHands(e.target.value as typeof openHands)}>
              <option value="default">Per rulebook (open when introductory)</option>
              <option value="open">Open hands</option>
              <option value="closed">Hidden hands</option>
            </select>
          </label>
          <label className="field">
            Event card windows
            <select value={windows} onChange={(e) => setWindows(e.target.value)}>
              <option value="checkpoints">Checkpoints (before draw, before infection...)</option>
              <option value="full">Full (also before every action)</option>
              <option value="off">Off (events only on your own turn)</option>
            </select>
          </label>
          <label className="check">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            Require consent for card sharing and moving other pawns
          </label>
          <label className="field">
            Timeout for unanswered prompts (seconds, optional)
            <input
              value={timeout}
              onChange={(e) => setTimeoutS(e.target.value)}
              inputMode="numeric"
              placeholder="none"
            />
          </label>
          <button className="primary" disabled={busy}>
            Create room
          </button>
        </form>
        <form className="card" onSubmit={join}>
          <h2>Join a room</h2>
          <label className="field">
            Room code
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. a1b2c3" />
          </label>
          <button className="primary" disabled={busy || !code.trim()}>
            Join
          </button>
        </form>
      </div>
    </div>
  );
}

export function JoinForm({ room, onEnter, onBack }: { room: string; onEnter: Enter; onBack: () => void }) {
  const [name, setNm] = useState(getName);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (ev: FormEvent) => {
    ev.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await joinAndEnter(room, name.trim() || "Player", onEnter);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="home">
      <h1>Pandemic</h1>
      <form className="card" onSubmit={submit}>
        <h2>Join room {room}</h2>
        {err && <div className="banner bad">{err}</div>}
        <label className="field">
          Your name
          <input value={name} onChange={(e) => setNm(e.target.value)} maxLength={20} autoFocus />
        </label>
        <div className="row">
          <button className="primary" disabled={busy}>
            Join
          </button>
          <button type="button" onClick={onBack}>
            Back
          </button>
        </div>
      </form>
    </div>
  );
}
