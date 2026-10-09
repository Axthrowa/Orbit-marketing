import { useCallback, useEffect, useState } from "react";

import { errorMessage, formatDateTime, timeAgo } from "../lib/format";
import { useAdmin } from "../state/AdminContext";
import { useEngine } from "../state/EngineContext";
import type { InboxItem, NotificationRow, Tone } from "../types";
import { Badge, Button, Card, EmptyState } from "./ui";

const TONE: Record<NotificationRow["status"], Tone> = {
  sent: "success",
  pending: "info",
  failed: "danger",
  suppressed: "neutral",
  no_target: "warning",
};
export const NOTICE_LABEL: Record<NotificationRow["status"], string> = {
  sent: "Gönderildi",
  pending: "Sırada",
  failed: "Başarısız",
  suppressed: "Gönderilmedi",
  no_target: "Hedef yok",
};
const KIND: Record<string, string> = { strike: "Hareketsizlik uyarısı", flag: "Yönetici eskalasyonu" };

function viewerOf(isAdmin: boolean, userId: number | null): { admin: true } | { userId: number } | null {
  if (isAdmin) return { admin: true };
  return userId ? { userId } : null;
}

/** Uygulama içi gelen kutusu: kullanıcı kendi uyarılarını, yönetici eskalasyonları görür. */
function Inbox({ isAdmin, userId }: { isAdmin: boolean; userId: number | null }) {
  const { engine, state, reload, toast } = useEngine();
  const admin = useAdmin();
  const [items, setItems] = useState<InboxItem[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const viewer = viewerOf(isAdmin, userId);
    if (!viewer) return;
    try {
      const result = isAdmin
        ? await admin.run("Yönetici gelen kutusu için doğrulama gerekir", (pin) => engine.inbox(viewer, pin))
        : await engine.inbox(viewer, null);
      if (result) setItems(result.items);
    } catch (caught) {
      toast("danger", errorMessage(caught));
    }
  }, [isAdmin, userId, engine, admin, toast]);

  useEffect(() => {
    void load();
  }, [load, state?.inbox_unread]);

  const markRead = async (ids: number[] | null) => {
    const viewer = viewerOf(isAdmin, userId);
    if (!viewer) return;
    setBusy(true);
    try {
      const marked = isAdmin
        ? await admin.run("Yönetici gelen kutusu için doğrulama gerekir", (pin) => engine.inboxRead(viewer, ids, pin))
        : await engine.inboxRead(viewer, ids, null);
      if (marked !== null) await Promise.all([load(), reload()]);
    } catch (caught) {
      toast("danger", errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const unread = items.filter((i) => !i.read_at).length;
  return (
    <Card
      kicker={isAdmin ? "Yönetici gelen kutusu" : "Gelen kutum"}
      title={unread > 0 ? `${unread} okunmamış bildirim` : "Tüm bildirimler okundu"}
      actions={
        unread > 0 ? (
          <Button small busy={busy} onClick={() => void markRead(null)}>
            Tümünü okundu say
          </Button>
        ) : undefined
      }
    >
      {items.length === 0 ? (
        <EmptyState title="Gelen kutusu boş">Uyarılar ve özetler burada da görünür; Telegram/e-posta kapalı olsa bile.</EmptyState>
      ) : (
        <div className="grid gap-3">
          {items.map((item) => (
            <article key={item.id} className={item.read_at ? "alert" : "recommendation"}>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <strong>{item.title}</strong>
                  <span className="flex items-center gap-2">
                    {item.read_at ? <Badge tone="neutral">Okundu</Badge> : <Badge tone="info">Yeni</Badge>}
                    <span className="muted text-[11px]">{timeAgo(item.created_at)}</span>
                  </span>
                </div>
                <p className="mt-1 whitespace-pre-line text-[12px]">{item.body}</p>
                {!item.read_at ? (
                  <div className="mt-2">
                    <Button small variant="ghost" disabled={busy} onClick={() => void markRead([item.id])}>
                      Okundu say
                    </Button>
                  </div>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      )}
    </Card>
  );
}

export function NotificationCenter({ isAdmin, userId }: { isAdmin: boolean; userId: number | null }) {
  return (
    <div className="grid gap-5">
      <Inbox isAdmin={isAdmin} userId={userId} />
      {isAdmin ? <DeliveryQueue /> : null}
    </div>
  );
}

const CHANNEL: Record<string, string> = { TELEGRAM: "Telegram", EMAIL: "E-posta", TEAMS: "Teams" };

function DeliveryQueue() {
  const { state } = useEngine();
  const rows = state?.notifications ?? [];
  const summary = state?.notification_summary ?? {};
  return (
    <Card
      kicker="Ekibin nabzı"
      title="Gönderim kuyruğu (Telegram · e-posta · Teams)"
      actions={
        <span className="muted text-[11px]">
          {Object.entries(summary)
            .map(([key, count]) => `${NOTICE_LABEL[key as NotificationRow["status"]] ?? key}: ${count}`)
            .join(" · ") || "boş"}
        </span>
      }
    >
      {rows.length === 0 ? (
        <EmptyState title="Henüz bildirim yok">Hareketsizlik uyarıları ve yönetici bildirimleri burada görünür.</EmptyState>
      ) : (
        <div className="grid gap-3">
          {rows.map((row) => (
            <article key={row.id} className={row.kind === "flag" ? "recommendation" : "alert"}>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <strong>
                    {KIND[row.kind] ?? row.kind} · {row.user_name ?? "—"}
                    {row.channel ? <span className="muted"> · {CHANNEL[row.channel] ?? row.channel}</span> : null}
                  </strong>
                  <Badge tone={TONE[row.status]}>{NOTICE_LABEL[row.status]}</Badge>
                </div>
                <div className="muted mt-1 text-[11px]">
                  {formatDateTime(row.created_at)}
                  {row.attempts > 0 ? ` · ${row.attempts} deneme` : ""}
                  {row.last_error ? ` · ${row.last_error}` : row.status === "no_target" ? " · alıcı adresi tanımlı değil" : ""}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </Card>
  );
}
