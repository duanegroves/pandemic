import { useCallback, useEffect, useState } from "react";
import { Home, JoinForm } from "./components/Home";
import { RoomScreen } from "./components/RoomScreen";
import { type Session, clearSession, getMeta, loadSession } from "./lib/net";
import { MetaContext } from "./meta";
import type { Meta } from "./types";

function roomFromUrl(): string | null {
  return new URLSearchParams(location.search).get("room");
}

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaErr, setMetaErr] = useState<string | null>(null);
  const [roomId, setRoomId] = useState<string | null>(roomFromUrl);
  const [session, setSession] = useState<Session | null>(() => {
    const r = roomFromUrl();
    return r ? loadSession(r) : null;
  });

  useEffect(() => {
    getMeta().then(setMeta, (e) => setMetaErr(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    const onPop = () => {
      const r = roomFromUrl();
      setRoomId(r);
      setSession(r ? loadSession(r) : null);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const enter = useCallback((room: string, s: Session) => {
    history.pushState(null, "", `?room=${encodeURIComponent(room)}`);
    setRoomId(room);
    setSession(s);
  }, []);

  const leave = useCallback(() => {
    if (roomId) clearSession(roomId);
    history.pushState(null, "", location.pathname);
    setRoomId(null);
    setSession(null);
  }, [roomId]);

  if (metaErr) return <div className="center-msg">Could not load board data: {metaErr}</div>;
  if (!meta) return <div className="center-msg">Loading...</div>;

  let body;
  if (!roomId) body = <Home onEnter={enter} />;
  else if (!session) body = <JoinForm room={roomId} onEnter={enter} onBack={leave} />;
  else
    body = (
      <RoomScreen
        key={roomId + session.token}
        roomId={roomId}
        session={session}
        onLeave={leave}
        onDenied={() => {
          clearSession(roomId);
          setSession(null);
        }}
      />
    );
  return <MetaContext.Provider value={meta}>{body}</MetaContext.Provider>;
}
