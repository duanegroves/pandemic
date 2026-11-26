import type { Session } from "../lib/net";
import { useRoomSocket } from "../useRoomSocket";
import { Game } from "./Game";
import { Lobby } from "./Lobby";

interface Props {
  roomId: string;
  session: Session;
  onLeave: () => void;
  onDenied: () => void;
}

export function RoomScreen({ roomId, session, onLeave, onDenied }: Props) {
  const { view, send, sendAction } = useRoomSocket(roomId, session.token, onDenied);
  const conn =
    view.status === "open" ? null : (
      <div className="conn-banner">
        {view.status === "connecting" ? "Connecting..." : "Connection lost. Reconnecting..."}
      </div>
    );
  const toast = view.error && (
    <div className="toast" key={view.error.n} role="alert">
      {view.error.text}
    </div>
  );

  if (view.game && view.lobby) {
    return (
      <>
        {conn}
        {toast}
        <Game view={view} send={send} sendAction={sendAction} onLeave={onLeave} />
      </>
    );
  }
  return (
    <>
      {conn}
      {toast}
      <Lobby roomId={roomId} view={view} send={send} onLeave={onLeave} />
    </>
  );
}
