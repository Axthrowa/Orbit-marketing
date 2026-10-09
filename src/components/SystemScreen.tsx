import { useCallback, useEffect, useRef, useState } from "react";

import { errorMessage, formatDateTime, formatPercent, timeAgo } from "../lib/format";
import { useAdmin } from "../state/AdminContext";
import { useEngine } from "../state/EngineContext";
import type { ProviderHealth, SystemOverview, Tone } from "../types";
import { PlatformLogo } from "./PlatformLogo";
import { Alert, Badge, Button, Card, EmptyState } from "./ui";

const CIRCUIT: Record<ProviderHealth["circuit"], { label: string; tone: Tone }> = {
  CLOSED: { label: "Çalışıyor", tone: "success" },
  HALF_OPEN: { label: "Deneniyor", tone: "warning" },
  OPEN: { label: "Duraklatıldı", tone: "danger" },
};

const JOB_TONE: Record<string, Tone> = { ok: "success", error: "danger", running: "info" };
const JOB_STATUS: Record<string, string> = { ok: "Başarılı", error: "Hata", running: "Çalışıyor" };

/** Yönetici: arka plan işleri, sağlayıcı sağlığı, denetim günlüğü, uyarı geçmişi, dışa aktarma ve yedek. */
export function SystemScreen() {
  const { engine, reload, toast } = useEngine();
  const admin = useAdmin();
  const [data, setData] = useState<SystemOverview | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await admin.run("Sistem durumunu görmek için yönetici doğrulaması gerekir", (pin) => engine.systemOverview(pin));
      if (result !== null) {
        setData(result);
        setError(null);
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [admin, engine]);

  // Yalnızca ilk açılışta yüklenir; sonraki yenilemeler düğmelerle yapılır.
  const loaded = useRef(false);
  useEffect(() => {
    if (loaded.current) return;
    loaded.current = true;
    void load();
  }, [load]);

  const act = async (key: string, reason: string, action: (pin: string) => Promise<string>) => {
    setBusy(key);
    try {
      const message = await admin.run(reason, action);
      if (message !== null) {
        toast("success", message);
        await Promise.all([load(), reload()]);
      }
    } catch (caught) {
      toast("danger", errorMessage(caught));
    } finally {
      setBusy(null);
    }
  };

  const runJob = (name: string, label: string) =>
    act(`job:${name}`, `“${label}” işini şimdi çalıştırmak için yönetici doğrulaması gerekir`, async (pin) => {
      await engine.runJob(pin, name);
      return `${label} tamamlandı`;
    });

  return (
    <div className="grid gap-5">
      {error ? <Alert tone="danger" title="Sistem durumu yüklenemedi">{error}</Alert> : null}

      <Card
        kicker="Arka plan işleri"
        title="Zamanlanmış işler"
        actions={
          <Button small icon="refresh" onClick={() => void load()}>
            Yenile
          </Button>
        }
      >
        {!data ? (
          <EmptyState title="Yükleniyor…" />
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {Object.entries(data.jobs.latest).map(([name, job]) => (
              <article key={name} className="alert">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <strong>{job.label}</strong>
                    {job.status ? <Badge tone={JOB_TONE[job.status] ?? "neutral"}>{JOB_STATUS[job.status] ?? job.status}</Badge> : <Badge tone="neutral">Henüz çalışmadı</Badge>}
                  </div>
                  <div className="muted mt-1 text-[11px]">{job.started_at ? `Son çalışma ${timeAgo(job.started_at)}` : "Kayıt yok"}</div>
                  <div className="mt-2">
                    <Button small icon="arrow" busy={busy === `job:${name}`} onClick={() => void runJob(name, job.label)}>
                      Şimdi çalıştır
                    </Button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
        {data && data.jobs.items.length > 0 ? (
          <div className="table-wrap mt-4">
            <table style={{ minWidth: 720 }}>
              <thead>
                <tr>
                  <th>İş</th>
                  <th>Başlangıç</th>
                  <th>Tetikleyen</th>
                  <th>Durum</th>
                  <th>Ayrıntı</th>
                </tr>
              </thead>
              <tbody>
                {data.jobs.items.slice(0, 20).map((job) => (
                  <tr key={job.id}>
                    <td>{data.jobs.latest[job.name]?.label ?? job.name}</td>
                    <td>{formatDateTime(job.started_at)}</td>
                    <td>{job.trigger === "manual" ? "Elle" : "Zamanlayıcı"}</td>
                    <td>
                      <Badge tone={JOB_TONE[job.status] ?? "neutral"}>{JOB_STATUS[job.status] ?? job.status}</Badge>
                    </td>
                    <td className="muted">{job.detail ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>

      <Card kicker="Sağlayıcılar" title="Platform sağlığı" actions={<span className="muted text-[11px]">Engel görülen platform otomatik duraklatılır; koruma atlatılmaz</span>}>
        {!data || data.providers.length === 0 ? (
          <EmptyState title="Henüz ölçüm denemesi yok" />
        ) : (
          <div className="table-wrap">
            <table style={{ minWidth: 760 }}>
              <thead>
                <tr>
                  <th>Platform</th>
                  <th>Devre</th>
                  <th className="num">Başarı (7 gün)</th>
                  <th className="num">Deneme</th>
                  <th className="num">Sırada</th>
                  <th>Son başarı</th>
                  <th>Son hata</th>
                </tr>
              </thead>
              <tbody>
                {data.providers.map((p) => (
                  <tr key={p.platform}>
                    <td>
                      <PlatformLogo platform={p.platform} size={16} withName />
                    </td>
                    <td>
                      <Badge tone={CIRCUIT[p.circuit].tone}>{CIRCUIT[p.circuit].label}</Badge>
                      {p.paused_until ? <small>{formatDateTime(p.paused_until)} tarihine kadar</small> : null}
                    </td>
                    <td className="num">{formatPercent(p.success_rate)}</td>
                    <td className="num">{p.attempts_7d}</td>
                    <td className="num">{p.queue}</td>
                    <td>{p.last_success_at ? timeAgo(p.last_success_at) : "—"}</td>
                    <td className="muted">{p.last_error ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-3">
          <Button
            small
            busy={busy === "retry"}
            onClick={() =>
              void act("retry", "Başarısız işleri yeniden kuyruğa almak için yönetici doğrulaması gerekir", async (pin) => {
                const r = await engine.retryFailed(pin);
                return `${r.notifications} bildirim, ${r.posts} paylaşım yeniden kuyruğa alındı`;
              })
            }
          >
            Başarısızları yeniden dene
          </Button>
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card kicker="Uyarı geçmişi" title="Son uyarılar">
          {!data || data.warnings.length === 0 ? (
            <EmptyState title="Uyarı yok" />
          ) : (
            <div className="grid gap-2">
              {data.warnings.slice(0, 15).map((w) => (
                <div key={w.id} className="flex items-center justify-between gap-2 text-[12px]">
                  <span>
                    <strong>{w.user_name}</strong> <span className="muted">· {w.team_name ?? "Ekipsiz"} · {w.reason}</span>
                  </span>
                  <span className="flex items-center gap-2 whitespace-nowrap">
                    <Badge tone={w.strike_number >= 3 ? "danger" : "warning"}>{w.strike_number}. uyarı</Badge>
                    <span className="muted">{w.resolved_at ? "çözüldü" : timeAgo(w.triggered_at)}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card kicker="Denetim günlüğü" title="Kim, ne zaman, ne yaptı?">
          {!data || data.audit.length === 0 ? (
            <EmptyState title="Kayıt yok" />
          ) : (
            <div className="grid gap-2">
              {data.audit.slice(0, 15).map((a) => (
                <div key={a.id} className="flex items-center justify-between gap-2 text-[12px]">
                  <span className="min-w-0">
                    <strong>{a.actor}</strong> <span className="muted">· {a.action}{a.entity ? ` · ${a.entity} ${a.entity_id ?? ""}` : ""}</span>
                  </span>
                  <span className="muted whitespace-nowrap">{timeAgo(a.at)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card kicker="Veri" title="Dışa aktarma ve yedek" icon="download">
        <p className="muted mb-3 text-[12px]">
          Dışa aktarılan dosyalar İndirilenler klasörüne yazılır; formül enjeksiyonuna karşı hücreler temizlenir. Yedekler veri klasöründe
          tutulur ve eski yedekler ayardaki sayıya göre döndürülür.
        </p>
        <div className="flex flex-wrap gap-2">
          {(["xlsx", "csv", "json"] as const).map((format) => (
            <Button
              key={format}
              icon="download"
              busy={busy === `export:${format}`}
              onClick={() =>
                void act(`export:${format}`, "Dışa aktarmak için yönetici doğrulaması gerekir", async (pin) => {
                  const r = await engine.exportData(pin, format);
                  return `Kaydedildi: ${r.path}`;
                })
              }
            >
              {format.toUpperCase()} olarak dışa aktar
            </Button>
          ))}
          <Button
            variant="primary"
            busy={busy === "backup"}
            onClick={() =>
              void act("backup", "Yedek almak için yönetici doğrulaması gerekir", async (pin) => {
                const r = await engine.backup(pin);
                return `Yedek alındı: ${r.path}`;
              })
            }
          >
            Şimdi yedek al
          </Button>
          <Button
            busy={busy === "retention"}
            onClick={() =>
              void act("retention", "Saklama süresi temizliği için yönetici doğrulaması gerekir", async (pin) => {
                const r = await engine.retention(pin);
                const total = Object.values(r).reduce((a, b) => a + (typeof b === "number" ? b : 0), 0);
                return `Saklama temizliği tamamlandı (${total} kayıt)`;
              })
            }
          >
            Saklama temizliğini çalıştır
          </Button>
          <Button
            variant="ghost"
            busy={busy === "seed"}
            onClick={() =>
              void act("seed", "Örnek veri eklemek için yönetici doğrulaması gerekir", async (pin) => {
                await engine.seedDemo(pin);
                return "Örnek (MOCK) veriler eklendi";
              })
            }
          >
            Boş veritabanına örnek veri ekle
          </Button>
        </div>
      </Card>
    </div>
  );
}
