import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import type { Engine } from "../lib/engine";
import { errorMessage } from "../lib/format";
import type { EngineState, Tone } from "../types";

const POLL_MS = 60_000;
const TOAST_MS = 6_000;

interface Toast {
  id: number;
  tone: Tone;
  text: string;
}

interface EngineContextValue {
  engine: Engine;
  state: EngineState | null;
  loading: boolean;
  error: string | null;
  teamFilter: number | null;
  setTeamFilter: (teamId: number | null) => void;
  /** Kullanıcı hesabı görünümü: o kişinin kimliği; `null` = yönetici (herkes), 0 = henüz seçilmedi. */
  viewerUserId: number | null;
  setViewerUserId: (userId: number | null) => void;
  reload: () => Promise<void>;
  toast: (tone: Tone, text: string) => void;
}

const Context = createContext<EngineContextValue | null>(null);

export function EngineProvider({ engine, children }: { engine: Engine; children: ReactNode }) {
  const [state, setState] = useState<EngineState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [teamFilter, setTeamFilter] = useState<number | null>(null);
  const [viewerUserId, setViewerUserId] = useState<number | null>(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextToast = useRef(1);

  const reload = useCallback(async () => {
    try {
      setState(await engine.state(viewerUserId === null ? teamFilter : null, viewerUserId));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [engine, teamFilter, viewerUserId]);

  useEffect(() => {
    void reload();
    const timer = window.setInterval(() => {
      if (!document.hidden) void reload();
    }, POLL_MS);
    const onFocus = () => void reload();
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [reload]);

  const toast = useCallback((tone: Tone, text: string) => {
    const id = nextToast.current++;
    setToasts((current) => [...current.slice(-3), { id, tone, text }]);
    window.setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), TOAST_MS);
  }, []);

  const value = useMemo<EngineContextValue>(
    () => ({ engine, state, loading, error, teamFilter, setTeamFilter, viewerUserId, setViewerUserId, reload, toast }),
    [engine, state, loading, error, teamFilter, viewerUserId, reload, toast],
  );

  return (
    <Context.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" role="status">
        {toasts.map((item) => (
          <div key={item.id} className={item.tone === "danger" || item.tone === "warning" ? `toast toast-${item.tone}` : "toast"}>
            {item.text}
          </div>
        ))}
      </div>
    </Context.Provider>
  );
}

export function useEngine(): EngineContextValue {
  const value = useContext(Context);
  if (value === null) throw new Error("useEngine, EngineProvider içinde kullanılmalı");
  return value;
}
