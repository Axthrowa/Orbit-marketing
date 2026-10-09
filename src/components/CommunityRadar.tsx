import { Ban, Star } from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { errorMessage, formatCount, timeAgo } from "../lib/format";
import { useAdmin } from "../state/AdminContext";
import { useEngine } from "../state/EngineContext";
import type { RecommendationItem, Recommendations } from "../types";
import { PlatformLogo } from "./PlatformLogo";
import { Alert, Badge, Button, Card, EmptyState } from "./ui";

export function CommunityRadar({ onUse, isAdmin }: { onUse: (communityName: string) => void; isAdmin: boolean }) {
  const { engine, state, reload, toast } = useEngine();
  const admin = useAdmin();
  const [discovering, setDiscovering] = useState(false);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [gameId, setGameId] = useState<number | null>(null);
  const [campaignId, setCampaignId] = useState<number | null>(null);
  const [recs, setRecs] = useState<Recommendations | null>(null);
  const activeGames = (state?.games ?? []).filter((g) => g.status === "active");
  const activeCampaigns = (state?.campaigns ?? []).filter((c) => c.status === "active" || c.status === "planned");

  useEffect(() => {
    let alive = true;
    engine
      .recommendations({ gameId, campaignId })
      .then((result) => {
        if (alive) setRecs(result);
      })
      .catch((caught: unknown) => {
        if (alive) setError(errorMessage(caught));
      });
    return () => {
      alive = false;
    };
  }, [engine, gameId, campaignId, state?.generated_at]);
  const communities = recs?.items ?? [];

  const discover = async () => {
    setError(null);
    setDiscovering(true);
    try {
      const report = await admin.run("Topluluk keşfi çalıştırmak için yönetici doğrulaması gerekir", (pin) => engine.discover(pin));
      if (report) {
        if (report.unavailable.length > 0) toast("warning", `Kaynak kullanılamıyor: ${report.unavailable.join("; ")}`);
        else toast("success", `${report.added} yeni topluluk bulundu (${report.found} aday)`);
        await reload();
      }
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setDiscovering(false);
    }
  };

  const toggleFavorite = async (row: RecommendationItem) => {
    try {
      await engine.communityState(row.id, { favorite: row.favorite !== 1 }, null);
      await reload();
    } catch (caught) {
      toast("danger", errorMessage(caught));
    }
  };

  const block = async (row: RecommendationItem) => {
    try {
      const done = await admin.run(`“${row.name}” topluluğunu engellemek için yönetici doğrulaması gerekir`, (pin) =>
        engine.communityState(row.id, { status: "blocked" }, pin),
      );
      if (done !== null) {
        toast("info", `${row.name} engellendi; artık önerilmeyecek`);
        await reload();
      }
    } catch (caught) {
      toast("danger", errorMessage(caught));
    }
  };

  const add = async (event: FormEvent) => {
    event.preventDefault();
    if (!newName.trim()) return;
    try {
      await engine.addCommunity(newName.trim(), "Other");
      setNewName("");
      toast("success", "Topluluk eklendi");
      await reload();
    } catch (caught) {
      toast("danger", errorMessage(caught));
    }
  };

  return (
    <div className="stack">
      <Card kicker="Topluluk keşfi" title="Anahtar kelimelerden yeni topluluklar" icon="communities">
        <div className="flex flex-wrap items-end gap-3">
          <p className="muted m-0 min-w-[240px] flex-1 text-[12px]">
            Radar yalnızca keşif ve öneri yapar; hiçbir topluluğa otomatik paylaşım yapılmaz. Kuralları ve etkinliği paylaşmadan önce kendiniz kontrol
            edin. Anahtar kelimeler Bağlantılar & ayarlar ekranındadır.
          </p>
          <form onSubmit={(event) => void add(event)} className="flex gap-2">
            <input className="input" style={{ width: 220 }} placeholder="Topluluğu elle ekle…" value={newName} onChange={(event) => setNewName(event.target.value)} aria-label="Topluluğu elle ekle" />
            <Button type="submit" disabled={!newName.trim()}>
              Ekle
            </Button>
          </form>
          {isAdmin ? (
            <Button variant="primary" icon="communities" busy={discovering} onClick={() => void discover()}>
              Keşfi çalıştır
            </Button>
          ) : null}
        </div>
        {error ? (
          <div className="mt-3">
            <Alert tone="danger">{error}</Alert>
          </div>
        ) : null}
      </Card>

      <Card kicker="Öneri hedefi" title="Hangi oyun ya da kampanya için?" lift={false}>
        <div className="flex flex-wrap items-end gap-3">
          <label className="theme-control">
            Oyun
            <select aria-label="Öneri oyunu" value={gameId ?? ""} onChange={(event) => setGameId(event.target.value === "" ? null : Number(event.target.value))}>
              <option value="">Tüm oyunlar</option>
              {activeGames.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </label>
          <label className="theme-control">
            Kampanya
            <select aria-label="Öneri kampanyası" value={campaignId ?? ""} onChange={(event) => setCampaignId(event.target.value === "" ? null : Number(event.target.value))}>
              <option value="">Kampanya yok</option>
              {activeCampaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <span className="muted text-[11px]">
            Puan: konu uyumu, etkinlik, geçmiş etkileşim, tazelik, dil ve kitle uyumu; spam riski ve yakın kullanım düşürür.
          </span>
        </div>
      </Card>

      {communities.length === 0 ? (
        <Card>
          <EmptyState title="Henüz topluluk yok">“Keşfi çalıştır” ile topluluk bulun ya da elle ekleyin.</EmptyState>
        </Card>
      ) : (
        <div className="community-grid">
          {communities.map((row) => (
            <article key={row.id} className="panel lift community-card">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <PlatformLogo platform={row.platform} size={18} withName />
                {row.last_used ? <Badge tone="warning">Son kullanım {timeAgo(row.last_used)}</Badge> : <Badge tone="success">Hiç kullanılmadı</Badge>}
              </div>
              <h3>
                {row.favorite === 1 ? <Star size={15} aria-label="Favori" style={{ color: "var(--coral)", marginRight: 6, verticalAlign: -1 }} /> : null}
                {row.name}
              </h3>
              <ul className="m-0 grid gap-1 p-0 text-[12px]" style={{ listStyle: "none" }} aria-label="Öneri gerekçeleri">
                {row.reasons.map((reason) => (
                  <li key={reason.text} style={{ color: reason.tone === "plus" ? "var(--green)" : reason.tone === "minus" ? "var(--red)" : "var(--muted)" }}>
                    {reason.tone === "plus" ? "+ " : reason.tone === "minus" ? "− " : "· "}
                    {reason.text}
                  </li>
                ))}
              </ul>
              <div className="community-facts">
                <div>
                  {formatCount(row.member_count)}
                  <small>Üye</small>
                </div>
                <div>
                  {row.score.toFixed(0)}
                  <small>Öneri puanı</small>
                </div>
                <div>
                  {row.previous_posts}
                  <small>Önceki paylaşım</small>
                </div>
              </div>
              <div className="community-actions">
                <Button variant="primary" small icon="shares" onClick={() => onUse(row.name)}>
                  Burada paylaş
                </Button>
                <Button small variant="ghost" aria-label="Favori" title="Favori" onClick={() => void toggleFavorite(row)}>
                  <Star size={14} aria-hidden />
                </Button>
                {isAdmin ? (
                  <Button small variant="ghost" aria-label="Engelle" title="Engelle" onClick={() => void block(row)}>
                    <Ban size={14} aria-hidden />
                  </Button>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
