import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { errorMessage, formatCount, timeAgo } from "../lib/format";
import { useEngine } from "../state/EngineContext";
import type { AnalyticsOverview, BreakdownRow, ContentType, TopicCount } from "../types";
import { PlatformLogo } from "./PlatformLogo";
import { Alert, Avatar, Badge, Card, EmptyState, Field, Kpi } from "./ui";

const PERIODS: { value: number | null; label: string }[] = [
  { value: 1, label: "Son 24 saat" },
  { value: 7, label: "Son 7 gün" },
  { value: 30, label: "Son 30 gün" },
  { value: 90, label: "Son 90 gün" },
  { value: 365, label: "Son 1 yıl" },
  { value: null, label: "Tüm zamanlar" },
];

export const CONTENT_LABEL: Record<ContentType, string> = {
  post: "Gönderi",
  video: "Video",
  image: "Görsel",
  poll: "Anket",
  event: "Etkinlik",
  other: "Diğer",
};

export const COMPONENT_LABEL: Record<string, string> = {
  post_consistency: "Düzenli paylaşım",
  engagement_score: "Etkileşim",
  sentiment_score: "Oyuncu tepkisi",
  community_diversity: "Topluluk çeşitliliği",
  engagement_velocity: "Etkileşim hızı",
  campaign_contribution: "Kampanya katkısı",
};

function BreakdownTable({ title, rows, label }: { title: string; rows: BreakdownRow[]; label?: (row: BreakdownRow) => ReactNode }) {
  const max = Math.max(1, ...rows.map((r) => r.engagement ?? 0));
  return (
    <Card kicker="Kırılım" title={title}>
      {rows.length === 0 ? (
        <EmptyState title="Bu dönemde veri yok" />
      ) : (
        <div className="grid gap-2">
          {rows.map((row) => (
            <div key={String(row.key)}>
              <div className="flex items-center justify-between gap-2 text-[12px]">
                <span className="flex min-w-0 items-center gap-2 font-semibold">{label ? label(row) : (row.name ?? String(row.key))}</span>
                <span className="muted whitespace-nowrap">
                  {row.posts} paylaşım · {formatCount(row.engagement)} etkileşim
                </span>
              </div>
              <div className="bar mt-1" role="img" aria-label={`${formatCount(row.engagement)} etkileşim`}>
                <span className="bar-pos" style={{ width: `${((row.engagement ?? 0) / max) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

/** Analitik + lider tablosu: dönem, kampanya, oyun ve platform filtreleri motorda uygulanır. */
export function AnalyticsScreen({ userId, teamId }: { userId: number | null; teamId: number | null }) {
  const { engine, state } = useEngine();
  const [days, setDays] = useState<number | null>(30);
  const [campaignId, setCampaignId] = useState<number | null>(null);
  const [gameId, setGameId] = useState<number | null>(null);
  const [platform, setPlatform] = useState<string | null>(null);
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    engine
      .analytics({ days, campaign_id: campaignId, game_id: gameId, platform, team_id: teamId, user_id: userId })
      .then((result) => {
        if (!alive) return;
        setData(result);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (alive) setError(errorMessage(caught));
      });
    return () => {
      alive = false;
    };
  }, [engine, days, campaignId, gameId, platform, teamId, userId, state?.generated_at]);

  const platforms = [...new Set((state?.posts ?? []).map((p) => p.platform))];
  const totals = data?.totals;

  return (
    <div className="grid gap-5">
      <Card kicker="Filtreler" title="Hangi dönem, hangi kampanya?" lift={false}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Dönem" htmlFor="an-days">
            <select id="an-days" className="input" value={days === null ? "" : String(days)} onChange={(e) => setDays(e.target.value === "" ? null : Number(e.target.value))}>
              {PERIODS.map((p) => (
                <option key={p.label} value={p.value === null ? "" : String(p.value)}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Kampanya" htmlFor="an-campaign">
            <select id="an-campaign" className="input" value={campaignId ?? ""} onChange={(e) => setCampaignId(e.target.value === "" ? null : Number(e.target.value))}>
              <option value="">Tüm kampanyalar</option>
              {(state?.campaigns ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Oyun" htmlFor="an-game">
            <select id="an-game" className="input" value={gameId ?? ""} onChange={(e) => setGameId(e.target.value === "" ? null : Number(e.target.value))}>
              <option value="">Tüm oyunlar</option>
              {(state?.games ?? []).map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Platform" htmlFor="an-platform">
            <select id="an-platform" className="input" value={platform ?? ""} onChange={(e) => setPlatform(e.target.value || null)}>
              <option value="">Tüm platformlar</option>
              {platforms.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </Card>

      {error ? <Alert tone="danger" title="Analitik yüklenemedi">{error}</Alert> : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Paylaşım" value={formatCount(totals?.posts)} sub={`${totals?.active_days ?? 0} aktif gün`} icon="shares" iconTone={0} />
        <Kpi label="Toplam etkileşim" value={formatCount(totals?.engagement)} sub={`Ortalama ${formatCount(totals?.avg_engagement)}`} icon="heart" iconTone={1} />
        <Kpi label="İzlenme" value={formatCount(totals?.views)} sub="Bilinmeyen sayılar “—”" icon="chart" iconTone={2} />
        <Kpi label="Topluluk" value={formatCount(totals?.community_count)} sub="Farklı topluluk" icon="communities" iconTone={3} />
      </div>

      <Card kicker="Lider tablosu" title="Performans puanı" actions={<span className="muted text-[11px]">Ağırlıkları yönetici ayarlar</span>}>
        {!data || data.leaderboard.length === 0 ? (
          <EmptyState title="Sıralanacak kişi yok" />
        ) : (
          <div className="table-wrap">
            <table style={{ minWidth: 860 }}>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Kişi</th>
                  <th className="num">Puan</th>
                  <th className="num">Paylaşım</th>
                  <th className="num">Haftalık</th>
                  <th className="num">Etkileşim</th>
                  <th className="num">Topluluk</th>
                  <th className="num">Uyarı</th>
                  <th>Son aktivite</th>
                </tr>
              </thead>
              <tbody>
                {data.leaderboard.map((row) => (
                  <tr key={row.user_id}>
                    <td>{row.rank}</td>
                    <td>
                      <span className="person-cell">
                        <Avatar name={row.name} />
                        <span>
                          {row.name}
                          <small>{row.team_name ?? "Ekipsiz"}</small>
                        </span>
                      </span>
                    </td>
                    <td className="num" title={Object.entries(row.components).map(([k, v]) => `${COMPONENT_LABEL[k] ?? k}: %${Math.round(v * 100)}`).join("\n")}>
                      <strong>{row.performance_score.toFixed(1)}</strong>
                    </td>
                    <td className="num">{row.posts}</td>
                    <td className="num">{row.posts_per_week ?? "—"}</td>
                    <td className="num">{formatCount(row.engagement)}</td>
                    <td className="num">{row.community_count}</td>
                    <td className="num">
                      {row.current_warnings > 0 ? <Badge tone={row.current_warnings >= 3 ? "danger" : "warning"}>{row.current_warnings}</Badge> : row.warnings}
                    </td>
                    <td>{row.last_activity ? timeAgo(row.last_activity) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data ? (
          <p className="muted mt-3 text-[11px]">
            Ağırlıklar: {Object.entries(data.weights).map(([k, v]) => `${COMPONENT_LABEL[k] ?? k} %${Math.round(v * 100)}`).join(" · ")}
          </p>
        ) : null}
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <BreakdownTable
          title="Platformlar"
          rows={data?.platforms ?? []}
          label={(row) => (
            <>
              <PlatformLogo platform={String(row.key)} size={16} /> {String(row.key)}
            </>
          )}
        />
        <BreakdownTable title="İçerik türleri" rows={data?.content_types ?? []} label={(row) => CONTENT_LABEL[row.key as ContentType] ?? String(row.key)} />
        <BreakdownTable title="Kampanyalar" rows={data?.campaigns ?? []} />
        <BreakdownTable title="Oyunlar" rows={data?.games ?? []} />
        <BreakdownTable title="Topluluklar" rows={data?.communities ?? []} />
        <TopicsCard topics={data?.topics ?? []} />
      </div>
    </div>
  );
}

/** Yorumlarda öne çıkan konular (olumlu / nötr / olumsuz dağılımıyla). */
export function TopicsCard({ topics }: { topics: TopicCount[] }) {
  const topicMax = Math.max(1, ...topics.map((t) => t.count));
  return (
    <Card kicker="Oyuncunun sesi" title="Yorumlarda öne çıkan konular">
      {topics.length === 0 ? (
        <EmptyState title="Konu bulunamadı">Yorumlar toplandıkça konular burada görünür.</EmptyState>
      ) : (
        <div className="grid gap-2">
          {topics.map((topic) => (
            <div key={topic.key}>
              <div className="flex justify-between gap-2 text-[12px]">
                <span className="font-semibold">{topic.label}</span>
                <span className="muted">
                  {topic.count} yorum · {topic.positive} olumlu · {topic.negative} olumsuz
                </span>
              </div>
              <div className="bar mt-1" role="img" aria-label={`${topic.label}: ${topic.count} yorum`}>
                <span className="bar-pos" style={{ width: `${(topic.positive / topicMax) * 100}%` }} />
                <span className="bar-neu" style={{ width: `${(Math.max(0, topic.count - topic.positive - topic.negative) / topicMax) * 100}%` }} />
                <span className="bar-neg" style={{ width: `${(topic.negative / topicMax) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
