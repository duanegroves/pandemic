import { DISEASE_FILL } from "../lib/theme";
import { COLORS, type Observation } from "../types";

const RATE_TRACK = [2, 2, 2, 3, 3, 4, 4];

export function StatusPanel({ obs }: { obs: Observation }) {
  const known = obs.infection_deck.known_top;
  const fc = obs.infection_deck.forecast;
  return (
    <section className="panel status">
      <h3>Status</h3>
      <div className="track-row">
        <span className="track-label">Outbreaks</span>
        <div className="track">
          {Array.from({ length: 9 }, (_, i) => (
            <span key={i} className={"cell" + (i === obs.outbreaks ? " on" : "") + (i >= 6 ? " danger" : "")}>
              {i}
            </span>
          ))}
        </div>
      </div>
      <div className="track-row">
        <span className="track-label">Infection rate</span>
        <div className="track">
          {RATE_TRACK.map((r, i) => (
            <span key={i} className={"cell" + (i === obs.infection_rate_index ? " on" : "")}>
              {r}
            </span>
          ))}
        </div>
      </div>
      <table className="diseases">
        <thead>
          <tr>
            <th>Disease</th>
            <th>Cure</th>
            <th>Cubes left</th>
          </tr>
        </thead>
        <tbody>
          {COLORS.map((c) => (
            <tr key={c}>
              <td>
                <span className="swatch" style={{ background: DISEASE_FILL[c] }} /> {c}
              </td>
              <td className={"cure-" + obs.cures[c]}>
                {obs.cures[c] === "none" ? "-" : obs.cures[c] === "cured" ? "Cured" : "Eradicated"}
              </td>
              <td className={obs.supply[c] <= 4 ? "low" : ""}>{obs.supply[c]}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="kv">
        <span>Player deck</span>
        <b>{obs.player_deck.size}</b>
        <span>Epidemics left in deck</span>
        <b>{obs.player_deck.epidemics_remaining}</b>
        <span>Infection deck</span>
        <b>{obs.infection_deck.size}</b>
        <span>Research stations</span>
        <b>{obs.research_stations.length}/6</b>
      </div>
      {obs.one_quiet_night && <div className="banner good">One Quiet Night is active: next infection step is skipped.</div>}
      {known.length > 0 && (
        <div className="known">
          <b>Known top of infection deck</b> (each group is a set, top first):
          {known.map((set, i) => (
            <div key={i} className="chips">
              {set.map((c) => (
                <span key={c} className="chip">
                  {c}
                </span>
              ))}
            </div>
          ))}
        </div>
      )}
      {fc && (
        <div className="known">
          <b>Your Forecast order</b> (below the top {fc.cards_above}): {fc.order.join(", ")}
        </div>
      )}
      <details>
        <summary>Infection discard ({obs.infection_discard.length})</summary>
        <div className="chips">
          {[...obs.infection_discard].reverse().map((c, i) => (
            <span key={c + i} className="chip">
              {c}
            </span>
          ))}
        </div>
        {obs.infection_removed.length > 0 && (
          <p className="muted">Removed from game: {obs.infection_removed.join(", ")}</p>
        )}
      </details>
      <details>
        <summary>Player discard ({obs.player_discard.length})</summary>
        <div className="chips">
          {[...obs.player_discard].reverse().map((c, i) => (
            <span key={c + i} className="chip">
              {c}
            </span>
          ))}
        </div>
      </details>
    </section>
  );
}
