import { useEffect, useMemo, useState } from "react";
import {
  EVENT_KEYS,
  ROLE_LABEL,
  type Labeler,
  cureByColor,
  describeAction,
  describeConsent,
  groupActions,
  narrow,
  treatByColor,
} from "../lib/actions";
import { remaining } from "../lib/countdown";
import { DISEASE_FILL, ROLE_STYLE } from "../lib/theme";
import { MAP_H, MAP_W, cityPos } from "../lib/geo";
import { useCityMap } from "../meta";
import type { RoomView } from "../useRoomSocket";
import { COLORS, type Action, type Observation } from "../types";
import { Board } from "./Board";
import { Chooser } from "./Chooser";
import { ForecastModal } from "./Forecast";
import { EventLog, ChatBox } from "./Log";
import { Modal } from "./Modal";
import { PlayersPanel } from "./PlayersPanel";
import { StatusPanel } from "./StatusPanel";

interface Props {
  view: RoomView;
  send: (m: object) => boolean;
  sendAction: (a: Action) => boolean;
  onLeave: () => void;
}

interface ChooserState {
  title: string;
  actions: Action[];
  keys: string[];
  prompt?: Record<string, string>;
}

const KIND_LABEL: Record<string, string> = {
  actions: "taking actions",
  event_window: "an event card window",
  discard: "discarding to the hand limit",
  consent: "a consent request",
  forecast_order: "arranging the Forecast",
  game_over: "game over",
};

function useNow(active: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

export function Game({ view, send, sendAction, onLeave }: Props) {
  const { msg, receivedAt } = view.game!;
  const obs = msg.observation;
  const you = msg.you;
  const kind = msg.decision.kind;
  const owner = msg.decision.player;
  const cities = useCityMap();
  const names = useMemo(() => {
    const out: string[] = [];
    for (const s of view.lobby!.seats) out[s.seat] = s.name;
    return out;
  }, [view.lobby]);
  const labeler: Labeler = useMemo(
    () => ({
      you,
      player: (s) => {
        const role = obs.players[s]?.role;
        return `${names[s] ?? "Player " + (s + 1)}${role ? ` (${ROLE_LABEL[role] ?? role})` : ""}`;
      },
    }),
    [you, names, obs.players],
  );

  const legal = msg.legal_actions;
  const G = useMemo(() => groupActions(legal), [legal]);
  const mine = owner === you && legal.length > 0;
  const over = msg.phase === "over" || obs.game_over;

  const [pop, setPop] = useState<{ city: string } | null>(null);
  const [chooser, setChooser] = useState<ChooserState | null>(null);
  const [share, setShare] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [overDismissed, setOverDismissed] = useState(false);

  // any new server message invalidates transient UI state
  useEffect(() => {
    setPop(null);
    setChooser(null);
    setShare(false);
    setSel(null);
  }, [receivedAt]);

  const act = (a: Action) => {
    setPop(null);
    setChooser(null);
    setShare(false);
    sendAction(a);
  };

  /** Send directly if the candidates are fully determined; otherwise open the chooser. */
  const pickFrom = (title: string, actions: Action[], keys: string[], prompt?: Record<string, string>) => {
    const r = narrow(actions, keys, {});
    if ("done" in r) act(r.done);
    else if ("choice" in r) setChooser({ title, actions, keys, prompt });
  };

  const playEvent = (card: string) => {
    const acts = G.events.get(card);
    if (acts) pickFrom(`Play ${card}`, acts, EVENT_KEYS[card] ?? []);
  };

  const playable = useMemo(() => new Set(G.events.keys()), [G.events]);
  const discarding = mine && kind === "discard";

  const onCard = (card: string) => {
    if (discarding) setSel(card === sel ? null : card);
    else if (playable.has(card)) playEvent(card);
  };

  const chooserLabel = (key: string, v: unknown): string => {
    if (key === "pawn" || key === "to_player" || key === "from_player") return labeler.player(v as number);
    if (key === "relocate_from") return v == null ? "No relocation needed" : `Move station from ${v}`;
    if (key === "cards") return (v as string[]).join(", ");
    if (key === "color") return `${v} cure`;
    return String(v);
  };

  const deadline = remaining(msg.deadline_in, receivedAt, useNow(msg.deadline_in != null));
  const targets = useMemo(
    () => (mine && kind === "actions" ? new Set(G.byCity.keys()) : new Set<string>()),
    [mine, kind, G.byCity],
  );

  const cityColor = (c: string) => cities.get(c)?.color;
  // A player's colour everywhere in the UI is their pawn (role) colour.
  const colorOf = (seat: number) => ROLE_STYLE[obs.players[seat]?.role ?? ""]?.fill;
  const turnName = names[obs.current_player] ?? `Player ${obs.current_player + 1}`;

  // ---- banner ----
  let banner;
  if (over) banner = <b>Game over</b>;
  else if (mine) {
    const text: Record<string, string> = {
      actions: `Your turn: ${obs.actions_remaining} action${obs.actions_remaining === 1 ? "" : "s"} left`,
      event_window: `Event window (${String(msg.decision.context.checkpoint).replace(/_/g, " ")}): play an event card or pass`,
      discard: `Hand limit: discard down to ${msg.decision.context.limit ?? 7} cards`,
      consent: "Your consent is needed",
      forecast_order: "Arrange the top of the infection deck",
    };
    banner = <b>{text[kind] ?? kind}</b>;
  } else {
    banner = (
      <span>
        Waiting for <b>{owner != null ? (names[owner] ?? `Player ${owner + 1}`) : "..."}</b>:{" "}
        {KIND_LABEL[kind] ?? kind}. It is {turnName}&apos;s turn ({obs.actions_remaining} action
        {obs.actions_remaining === 1 ? "" : "s"} left).
      </span>
    );
  }

  const popActions = pop ? (G.byCity.get(pop.city) ?? []) : [];
  const overlay =
    pop &&
    (() => {
      const p = cityPos(pop.city);
      const right = p.x > MAP_W * 0.6;
      return (
        <div
          className="popover"
          style={{
            left: `${(p.x / MAP_W) * 100}%`,
            top: `${(p.y / MAP_H) * 100}%`,
            transform: `translate(${right ? "-100%" : "0"}, 18px)`,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="pop-head">
            <b>{pop.city}</b>
            <button className="x" onClick={() => setPop(null)} aria-label="Close">
              x
            </button>
          </div>
          {popActions.length === 0 ? (
            <div className="muted">No legal actions here{mine ? "" : " (not your decision)"}.</div>
          ) : (
            popActions.map((a, i) => (
              <button key={i} className="pop-act" onClick={() => act(a)}>
                {describeAction(a, labeler)}
              </button>
            ))
          )}
        </div>
      );
    })();

  const treat = treatByColor(G.treat);
  const cures = cureByColor(G.cure);
  const inActions = mine && kind === "actions";

  return (
    <div className="game" onClick={() => setPop(null)}>
      <header className="topbar">
        <h1>Pandemic</h1>
        <span className="muted">
          Room <b>{view.lobby!.room_id}</b> | Turn {obs.turn} | You: <b>{names[you]}</b> ({ROLE_LABEL[obs.players[you]?.role] ?? ""})
        </span>
        <span className="grow" />
        <button onClick={onLeave} title="Forget this seat in this tab">
          Leave
        </button>
      </header>

      <div className={"decision-banner" + (mine && !over ? " mine" : "")}>
        <div className="grow">{banner}</div>
        {deadline != null && !over && (
          <span className={"deadline" + (deadline < 10 ? " urgent" : "")}>{Math.ceil(deadline)}s</span>
        )}
      </div>

      {mine && kind === "discard" && (
        <div className="panel inline-panel">
          <span>
            {sel ? (
              <>
                Discard <b>{sel}</b>?
              </>
            ) : (
              "Select a card from your hand to discard."
            )}
          </span>
          <button
            className="primary"
            disabled={!sel || !G.discards.some((a) => a.card === sel)}
            onClick={() => {
              const a = G.discards.find((d) => d.card === sel);
              if (a) act(a);
            }}
          >
            Discard
          </button>
          {[...playable].map((c) => (
            <button key={c} onClick={() => playEvent(c)}>
              Play {c} instead
            </button>
          ))}
        </div>
      )}

      {mine && kind === "event_window" && (
        <div className="panel inline-panel">
          {[...playable].map((c) => (
            <button key={c} className="primary" onClick={() => playEvent(c)}>
              Play {c}
            </button>
          ))}
          {G.pass && <button onClick={() => act(G.pass!)}>Pass</button>}
        </div>
      )}

      <div className="main">
        <div className="left">
          <Board
            obs={obs}
            you={you}
            names={names}
            targets={targets}
            selected={pop?.city ?? highlight}
            onCity={(city) => {
              setHighlight(null);
              setPop({ city });
            }}
            overlay={overlay ? <div onClick={(e) => e.stopPropagation()}>{overlay}</div> : null}
          />

          <section className="panel actionbar">
            <div className="ab-head">
              <h3>Actions</h3>
              <span className={"remaining" + (inActions ? "" : " dim")}>
                {obs.actions_remaining} left
              </span>
            </div>
            {inActions || kind === "actions" ? (
              <div className="ab-buttons">
                {COLORS.map((c) => (
                  <button
                    key={c}
                    disabled={!inActions || !treat.has(c)}
                    onClick={() => treat.get(c) && act(treat.get(c)!)}
                  >
                    <span className="swatch" style={{ background: DISEASE_FILL[c] }} /> Treat {c}
                  </button>
                ))}
                <button
                  disabled={!inActions || G.build.length === 0}
                  onClick={() =>
                    pickFrom("Build research station", G.build, ["relocate_from"], {
                      relocate_from: "Six stations exist. Which one should be moved here?",
                    })
                  }
                >
                  Build station
                </button>
                <button
                  disabled={!inActions || G.give.length + G.take.length === 0}
                  onClick={() => setShare(true)}
                >
                  Share knowledge
                </button>
                <button
                  disabled={!inActions || G.cure.length === 0}
                  onClick={() => pickFrom("Discover a cure", G.cure, ["color", "cards"], { cards: "Which cards to discard?" })}
                >
                  Discover cure{cures.size ? ` (${[...cures.keys()].join(", ")})` : ""}
                </button>
                {G.takeEvent.length > 0 && (
                  <button
                    disabled={!inActions}
                    onClick={() => pickFrom("Take an event card from the discard pile", G.takeEvent, ["card"])}
                  >
                    Take event card
                  </button>
                )}
                <button className="warn" disabled={!inActions || !G.end} onClick={() => G.end && act(G.end)}>
                  End actions
                </button>
              </div>
            ) : (
              <p className="muted">Actions are available during your action phase. Click a city for moves.</p>
            )}
            {inActions && G.byCity.size > 0 && (
              <p className="muted small">
                Highlighted cities can be reached or built in: click one to see how. Event cards in your hand are
                clickable.
              </p>
            )}
            {legal.length > 0 && (
              <details className="fallback">
                <summary>All legal actions ({legal.length})</summary>
                <div className="fallback-list">
                  {legal.slice(0, 150).map((a, i) => (
                    <button key={i} onClick={() => act(a)}>
                      {describeAction(a, labeler)}
                    </button>
                  ))}
                  {legal.length > 150 && <span className="muted">... and {legal.length - 150} more</span>}
                </div>
              </details>
            )}
          </section>

          <div className="logs">
            <section className="panel">
              <h3>Event log</h3>
              <EventLog
                log={view.log}
                name={(seat) => (seat === you ? "You" : (names[seat] ?? `Player ${seat + 1}`))}
                colorOf={colorOf}
              />
            </section>
            <section className="panel">
              <h3>Chat</h3>
              <ChatBox
                chat={view.chat}
                send={send}
                colorOf={colorOf}
              />
            </section>
          </div>
        </div>

        <aside className="right">
          <StatusPanel obs={obs} />
          <PlayersPanel
            obs={obs}
            names={names}
            you={you}
            playable={playable}
            selected={sel}
            selectable={discarding}
            onCard={onCard}
            onLocate={(c) => {
              setPop(null);
              setHighlight(c);
              setTimeout(() => setHighlight((h) => (h === c ? null : h)), 2500);
            }}
          />
        </aside>
      </div>

      {chooser && (
        <Chooser
          {...chooser}
          label={chooserLabel}
          onPick={act}
          onClose={() => setChooser(null)}
        />
      )}

      {share && (
        <Modal title="Share knowledge" onClose={() => setShare(false)}>
          <div className="options col">
            {[...G.give, ...G.take].map((a, i) => (
              <button key={i} onClick={() => act(a)}>
                {describeAction(a, labeler)}
              </button>
            ))}
          </div>
        </Modal>
      )}

      {mine && kind === "consent" && (
        <Modal title="Consent requested">
          <p>
            {describeConsent(
              msg.decision.context.requester as number,
              msg.decision.context.request as Action,
              labeler,
            )}
          </p>
          <div className="row">
            {G.consent
              .filter((a) => a.accept)
              .map((a) => (
                <button key="y" className="primary" onClick={() => act(a)}>
                  Accept
                </button>
              ))}
            {G.consent
              .filter((a) => !a.accept)
              .map((a) => (
                <button key="n" onClick={() => act(a)}>
                  Decline
                </button>
              ))}
          </div>
        </Modal>
      )}

      {mine && kind === "forecast_order" && (
        <ForecastModal
          key={(msg.decision.context.cards as string[]).join("|")}
          cards={msg.decision.context.cards as string[]}
          legal={G.forecast}
          cityColor={cityColor}
          onSubmit={act}
        />
      )}

      {over && !overDismissed && (
        <GameOver outcome={msg.outcome ?? obs.outcome} obs={obs} onLeave={onLeave} onClose={() => setOverDismissed(true)} />
      )}
    </div>
  );
}

function GameOver({
  outcome,
  obs,
  onLeave,
  onClose,
}: {
  outcome: { result: string; reason: string } | null;
  obs: Observation;
  onLeave: () => void;
  onClose: () => void;
}) {
  const win = outcome?.result === "win";
  const reasons: Record<string, string> = {
    outbreaks: "Too many outbreaks: the world panicked.",
    cube_shortage: "A disease ran out of cubes and spread beyond control.",
    player_deck_exhausted: "The player deck ran out before all cures were found.",
    all_diseases_cured: "All four diseases have been cured.",
  };
  return (
    <Modal title={win ? "Victory!" : "Defeat"} onClose={onClose}>
      <div className={"gameover " + (win ? "win" : "loss")}>
        <p className="big">{win ? "You cured the world." : "The world was lost."}</p>
        <p>{outcome ? (reasons[outcome.reason] ?? outcome.reason.replace(/_/g, " ")) : ""}</p>
        <p className="muted">
          Turn {obs.turn} | Outbreaks {obs.outbreaks}/8 | Cures:{" "}
          {COLORS.filter((c) => obs.cures[c] !== "none").join(", ") || "none"}
        </p>
        <div className="row">
          <button className="primary" onClick={onLeave}>
            Back to start
          </button>
          <button onClick={onClose}>View final board</button>
        </div>
      </div>
    </Modal>
  );
}
