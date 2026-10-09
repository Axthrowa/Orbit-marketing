import { KeyRound } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { Alert, Button, Field } from "../components/ui";
import { EngineError } from "../lib/engine";
import { errorMessage } from "../lib/format";
import { useEngine } from "./EngineContext";

interface PinRequest {
  reason: string;
  resolve: (pin: string | null) => void;
}

interface AdminContextValue {
  unlocked: boolean;
  /** Yönetici işlemi: PIN'i (gerekirse sorarak) alır, `action`'ı çalıştırır. İptalde null döner. */
  run: <T>(reason: string, action: (pin: string) => Promise<T>) => Promise<T | null>;
  lock: () => void;
}

const Context = createContext<AdminContextValue | null>(null);
const MIN_PIN = 6;

export function AdminProvider({ children }: { children: ReactNode }) {
  const { engine, state, reload, toast } = useEngine();
  const pinRef = useRef<string | null>(null);
  const [unlocked, setUnlocked] = useState(false);
  const [request, setRequest] = useState<PinRequest | null>(null);
  const pinSet = state?.security.pin_set ?? true;

  const ask = useCallback(
    (reason: string) =>
      new Promise<string | null>((resolve) => {
        setRequest({ reason, resolve });
      }),
    [],
  );

  const lock = useCallback(() => {
    pinRef.current = null;
    setUnlocked(false);
  }, []);

  const run = useCallback(
    async <T,>(reason: string, action: (pin: string) => Promise<T>): Promise<T | null> => {
      const pin = pinRef.current ?? (await ask(reason));
      if (pin === null) return null;
      try {
        return await action(pin);
      } catch (caught) {
        if (caught instanceof EngineError && caught.code === "PERMISSION_DENIED") lock();
        throw caught;
      }
    },
    [ask, lock],
  );

  const finish = (pin: string | null) => {
    if (pin !== null) {
      pinRef.current = pin;
      setUnlocked(true);
    }
    request?.resolve(pin);
    setRequest(null);
  };

  const value = useMemo(() => ({ unlocked, run, lock }), [unlocked, run, lock]);

  return (
    <Context.Provider value={value}>
      {children}
      {request ? (
        <PinDialog
          reason={request.reason}
          creating={!pinSet}
          verify={async (pin) => {
            await engine.verifyPin(pin);
          }}
          create={async (pin) => {
            await engine.setPin(pin, null);
            await reload();
            toast("success", "Yönetici PIN'i belirlendi");
          }}
          onDone={finish}
        />
      ) : null}
    </Context.Provider>
  );
}

function PinDialog({
  reason,
  creating,
  verify,
  create,
  onDone,
}: {
  reason: string;
  creating: boolean;
  verify: (pin: string) => Promise<void>;
  create: (pin: string) => Promise<void>;
  onDone: (pin: string | null) => void;
}) {
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (creating) {
      if (pin.length < MIN_PIN) return setError(`PIN en az ${MIN_PIN} karakter olmalı`);
      if (pin !== confirm) return setError("PIN'ler eşleşmiyor");
    }
    setBusy(true);
    try {
      if (creating) await create(pin);
      else await verify(pin);
      onDone(pin);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="drawer-scrim" style={{ zIndex: 50 }} onClick={() => onDone(null)} aria-hidden />
      <form className="modal" onSubmit={(event) => void submit(event)} aria-label="Yönetici girişi">
        <div className="card-head">
          <h2 className="card-title m-0 flex items-center gap-2">
            <KeyRound size={14} aria-hidden /> {creating ? "Yönetici PIN'i belirle" : "Yönetici PIN'i"}
          </h2>
        </div>
        <div className="card-body flex flex-col gap-3">
          <div className="muted">{reason}</div>
          {creating ? (
            <Alert tone="info">
              Henüz PIN yok. Yönetici işlemlerini korumak için en az {MIN_PIN} karakterlik bir PIN belirleyin.
              Bu yerel bir kapıdır; disk erişimi olan birine karşı güvenlik sınırı değildir.
            </Alert>
          ) : null}
          <Field label={creating ? "Yeni PIN" : "PIN"} htmlFor="pin">
            <input
              id="pin"
              className="input"
              type="password"
              autoFocus
              autoComplete="off"
              value={pin}
              onChange={(event) => setPin(event.target.value)}
            />
          </Field>
          {creating ? (
            <Field label="PIN (tekrar)" htmlFor="pin2">
              <input
                id="pin2"
                className="input"
                type="password"
                autoComplete="off"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
              />
            </Field>
          ) : null}
          {error ? <Alert tone="danger">{error}</Alert> : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => onDone(null)}>
              Vazgeç
            </Button>
            <Button variant="primary" type="submit" busy={busy} disabled={pin.length === 0}>
              {creating ? "PIN'i kaydet" : "Doğrula"}
            </Button>
          </div>
        </div>
      </form>
    </>
  );
}

export function useAdmin(): AdminContextValue {
  const value = useContext(Context);
  if (value === null) throw new Error("useAdmin, AdminProvider içinde kullanılmalı");
  return value;
}
