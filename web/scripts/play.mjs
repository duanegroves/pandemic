// Sanity player / fixture capture. Plays full games over REST + WebSocket exactly as the UI does.
// usage: node scripts/play.mjs [--base http://localhost:8010] [--players 2] [--games 1]
//        [--windows full|checkpoints|off] [--consent] [--capture src/__fixtures__/samples.json]
import { writeFileSync } from "node:fs";

const args = process.argv.slice(2);
const opt = (k, d) => {
  const i = args.indexOf("--" + k);
  return i >= 0 ? args[i + 1] : d;
};
const flag = (k) => args.includes("--" + k);
const base = opt("base", "http://localhost:8010");
const players = Number(opt("players", 2));
const games = Number(opt("games", 1));
const windows = opt("windows", "checkpoints");
const difficulty = opt("difficulty", "introductory");
const capturePath = opt("capture", null);
const wsBase = base.replace(/^http/, "ws");

const samples = {}; // key -> state message
function capture(m) {
  const keys = [`decision:${m.decision.kind}`];
  for (const a of m.legal_actions) keys.push(`action:${a.type}`);
  if (m.events.length) for (const e of m.events) keys.push(`event:${e.type}`);
  for (const k of keys) if (!samples[k] && Object.keys(samples).length < 80) samples[k] = m;
}

async function playGame(n) {
  const r = await fetch(`${base}/rooms`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      config: { num_players: players, difficulty, event_windows: windows, auto_consent: !flag("consent") },
    }),
  });
  const { room_id } = await r.json();
  const seats = [];
  for (let i = 0; i < players; i++) {
    const j = await (
      await fetch(`${base}/rooms/${room_id}/join`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: "bot" + i }),
      })
    ).json();
    seats.push(j);
  }
  let steps = 0;
  const done = new Promise((resolve, reject) => {
    let finished = 0;
    seats.forEach((s, i) => {
      const ws = new WebSocket(`${wsBase}/ws/${room_id}?token=${s.token}`);
      ws.onopen = () => ws.send(JSON.stringify({ type: "ready", ready: true }));
      ws.onerror = (e) => reject(new Error("ws error " + e.message));
      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.type === "lobby") {
          if (m.phase === "lobby" && i === 0 && m.seats.length === players && m.seats.every((x) => x.ready))
            ws.send(JSON.stringify({ type: "start" }));
        } else if (m.type === "state") {
          if (capturePath) capture(m);
          if (m.phase === "over") {
            ws.close();
            if (++finished === players) resolve(m);
          } else if (m.legal_actions.length) {
            steps++;
            // random policy, but prefer ending forecast/consent quickly
            const acts = m.legal_actions;
            let pick = acts[Math.floor(Math.random() * acts.length)];
            if (m.decision.kind === "actions" && Math.random() < 0.15) pick = acts.find((a) => a.type === "end_actions") ?? pick;
            ws.send(JSON.stringify({ type: "action", action: pick }));
          }
        } else if (m.type === "error") {
          reject(new Error(`server error ${m.code}: ${m.message}`));
        }
      };
    });
  });
  const final = await done;
  console.log(`game ${n} room ${room_id}: ${final.outcome.result} (${final.outcome.reason}) after ${steps} actions`);
}

for (let g = 1; g <= games; g++) await playGame(g);
if (capturePath) {
  writeFileSync(capturePath, JSON.stringify(samples));
  console.log("captured", Object.keys(samples).length, "samples:", Object.keys(samples).join(", "));
}
process.exit(0);
