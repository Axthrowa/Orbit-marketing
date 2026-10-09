import { useMemo } from "react";

import type { Tab } from "../App";
import { formatCount, formatPercent, timeAgo } from "../lib/format";
import { useEngine } from "../state/EngineContext";
import type { EngineState, PostRow, ProviderRow } from "../types";
import { PlatformLogo } from "./PlatformLogo";
import { Alert, Avatar, Badge, Button, Card, EmptyState, Kpi } from "./ui";

const DAY_MS = 86_400_000;

function engagementOf(post: Pick<PostRow, "likes" | "comments" | "shares">): number | null {
  if (post.likes === null && post.comments === null && post.shares === null) return null;
  return (post.likes ?? 0) + (post.comments ?? 0) + (post.shares ?? 0);
}

export function Dashboard({ onNavigate }: { onNavigate: (tab: Tab) => void }) {
  const { state, loading, error } = useEngine();

  if (state === null) {
    return error ? (
      <Alert tone="danger" title="Motor yanıt vermiyor">
        {error}
      </Alert>
    ) : (
      <p className="muted">{loading ? "Yükleniyor…" : ""}</p>
    );
  }

  const { kpis } = state;
  const engagement = engagementOf(kpis);
  const flagged = state.people.filter((p) => p.status === "flagged");

  return (
    <div className="stack">
      {error ? <Alert tone="warning" title="Veriler güncellenemedi">{error}</Alert> : null}
      {flagged.length > 0 ? (
        <Alert
          tone="danger"
          title={`${flagged.length} kullanıcı yönetici incelemesi bekliyor`}
          actions={
            <Button small variant="danger" onClick={() => onNavigate("team")}>
              Ekip yönetimine git
            </Button>
          }
        >
          {flagged.map((p) => `${p.name} (${p.team_name ?? "Ekipsiz"})`).join(", ")}
        </Alert>
      ) : null}

      <div>
        <span className="small-label">Ekibin toplamı</span>
        <div className="weekly-cards">
          <Kpi label="Paylaşım" value={formatCount(kpis.posts)} sub={kpis.posts_without_metrics > 0 ? `${kpis.posts_without_metrics} tanesi henüz ölçülmedi` : "tümü ölçüldü"} icon="campaigns" iconTone={0} />
          <Kpi label="Etkileşim" value={formatCount(engagement)} sub="beğeni + yorum + paylaşım" icon="heart" iconTone={2} />
          <Kpi label="İzlenme" value={formatCount(kpis.views)} sub={kpis.views === null ? "bilinmiyor" : "bilinenlerin toplamı"} icon="chart" iconTone={1} />
          <Kpi label="Olumlu tepki" value={formatPercent(kpis.avg_positive)} sub={`olumsuz ${formatPercent(kpis.avg_negative)}`} icon="audience" iconTone={3} />
          <Kpi label="İnceleme gereken" value={formatCount(kpis.users_flagged)} tone={kpis.users_flagged > 0 ? "danger" : undefined} sub={`${kpis.users_active}/${kpis.users_total} kişi aktif`} icon="management" iconTone={4} />
        </div>
        <p className="analytics-note">
          Toplamlar son ölçülen değerlerdir. — bilinmeyen veridir, sıfır değildir. Elle girilen sayılar “Elle girildi” etiketiyle ayrılır.
        </p>
      </div>

      <div className="dashboard-grid">
        <Card kicker="Etkileşimin yolculuğu" title="Son 7 günün nabzı" actions={<span className="muted text-[10px]">Paylaşım gününe göre</span>}>
          <WeeklyChart posts={state.posts} />
        </Card>
        <Card kicker="Ekibin ritmi" title="Takip durumu" icon="arrow" flush>
          <Rhythm people={state.people} />
        </Card>
      </div>

      <div className="analysis-grid">
        <Card kicker="Emeğin görünür olsun" title="Performans özeti" flush>
          <PerformanceTable state={state} />
        </Card>
        <Card kicker="Doğru topluluklar" title="Topluluk performansı" flush>
          <CommunityTable posts={state.posts} />
        </Card>
      </div>

      <div className="analysis-grid">
        <Card kicker="Bir sonraki adım" title="Veriden fikre" icon="arrow">
          <Recommendations state={state} />
        </Card>
        <Card kicker="Bağlantılar" title="Platform durumu" flush>
          <ProviderList providers={state.providers} />
        </Card>
      </div>
    </div>
  );
}

function WeeklyChart({ posts }: { posts: PostRow[] }) {
  const days = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return Array.from({ length: 7 }, (_, index) => {
      const start = today.getTime() - (6 - index) * DAY_MS;
      const inDay = posts.filter((p) => {
        const time = new Date(p.posted_at).getTime();
        return time >= start && time < start + DAY_MS;
      });
      const known = inDay.map(engagementOf).filter((v): v is number => v !== null);
      return {
        label: new Date(start).toLocaleDateString("tr-TR", { weekday: "short" }),
        count: inDay.length,
        engagement: known.length > 0 ? known.reduce((a, b) => a + b, 0) : null,
      };
    });
  }, [posts]);

  if (days.every((d) => d.count === 0)) {
    return <EmptyState title="Son 7 günde paylaşım yok">Yeni linkler eklendikçe günlük etkileşim burada görünür.</EmptyState>;
  }
  const width = 640;
  const height = 220;
  const top = 18;
  const bottom = 28;
  const max = Math.max(1, ...days.map((d) => d.engagement ?? 0));
  const slot = width / days.length;
  const barWidth = Math.min(46, slot * 0.5);
  const scale = (value: number) => ((height - top - bottom) * value) / max;
  return (
    <div className="weekly-chart" style={{ padding: 0 }}>
      <div className="chart-legend">
        <span>
          <i style={{ background: "var(--purple)" }} />
          Etkileşim
        </span>
        <span>
          <i style={{ background: "var(--coral)" }} />
          Paylaşım sayısı
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Son 7 günün etkileşimi">
        {[0.25, 0.5, 0.75, 1].map((ratio) => (
          <line key={ratio} x1="0" x2={width} y1={height - bottom - (height - top - bottom) * ratio} y2={height - bottom - (height - top - bottom) * ratio} stroke="var(--line)" />
        ))}
        {days.map((day, index) => {
          const x = index * slot + (slot - barWidth) / 2;
          const value = day.engagement ?? 0;
          const barHeight = Math.max(day.engagement === null ? 0 : 3, scale(value));
          return (
            <g key={day.label + index}>
              <rect x={x} y={height - bottom - barHeight} width={barWidth} height={barHeight} rx="7" fill="var(--purple)" opacity={day.engagement === null ? 0.25 : 0.9} />
              <text x={index * slot + slot / 2} y={height - 8} textAnchor="middle" fill="var(--muted)">
                {day.label}
              </text>
              {day.count > 0 ? (
                <text x={index * slot + slot / 2} y={height - bottom - barHeight - 6} textAnchor="middle" fill="var(--ink)" fontWeight="650">
                  {day.engagement === null ? "—" : formatCount(day.engagement)}
                </text>
              ) : null}
              {day.count > 0 ? <circle cx={index * slot + slot / 2 + barWidth / 2 + 8} cy={height - bottom - 6} r="9" fill="var(--coral-light)" /> : null}
              {day.count > 0 ? (
                <text x={index * slot + slot / 2 + barWidth / 2 + 8} y={height - bottom - 2.5} textAnchor="middle" fill="var(--coral)" fontWeight="700">
                  {day.count}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function Rhythm({ people }: { people: EngineState["people"] }) {
  const active = people.filter((p) => p.status === "active");
  const current = active.filter((p) => p.strike_count === 0).length;
  const warned = active.filter((p) => p.strike_count > 0);
  const flagged = people.filter((p) => p.status === "flagged").length;
  return (
    <>
      <div className="rhythm-stats">
        <div>
          <strong>{people.length}</strong>
          <span>Kişi</span>
        </div>
        <div>
          <strong style={{ color: "var(--success)" }}>{current}</strong>
          <span>Güncel</span>
        </div>
        <div>
          <strong style={{ color: warned.length ? "var(--warning)" : undefined }}>{warned.length}</strong>
          <span>Uyarıda</span>
        </div>
        <div>
          <strong style={{ color: flagged ? "var(--danger)" : undefined }}>{flagged}</strong>
          <span>İşaretli</span>
        </div>
      </div>
      <div className="reminder-progress">
        {warned.length === 0 && flagged === 0 ? (
          <span>Herkes ritimde. Hatırlatma bekleyen kimse yok.</span>
        ) : (
          [...warned, ...people.filter((p) => p.status === "flagged")].map((p) => (
            <div key={p.id} className="progress-row">
              <span>
                {p.name} · {p.days_since_last_post === null ? "hiç paylaşım yok" : `${p.days_since_last_post} gündür paylaşım yok`}
              </span>
              <strong style={p.status === "flagged" ? { color: "var(--danger)" } : undefined}>
                {p.strike_count}/{p.max_strikes} uyarı
              </strong>
            </div>
          ))
        )}
      </div>
    </>
  );
}

function PerformanceTable({ state }: { state: EngineState }) {
  const rows = [...state.people].sort((a, b) => (b.engagement ?? -1) - (a.engagement ?? -1));
  if (rows.length === 0) return <EmptyState title="Henüz kişi yok">Ekip yönetiminden kişi ekleyin.</EmptyState>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Kişi</th>
            <th className="num">Kayıt</th>
            <th className="num">Beğeni</th>
            <th className="num">Yorum</th>
            <th className="num">İzlenme</th>
            <th className="num">Etkileşim</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.id}>
              <td>
                <span className="person-cell">
                  <Avatar name={p.name} />
                  <span>
                    {p.name}
                    <small>{p.team_name ?? "Ekipsiz"}</small>
                  </span>
                </span>
              </td>
              <td className="num">{p.posts}</td>
              <td className="num">{formatCount(p.likes)}</td>
              <td className="num">{formatCount(p.comments)}</td>
              <td className="num">{formatCount(p.views)}</td>
              <td className="num font-semibold">{formatCount(p.engagement)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CommunityTable({ posts }: { posts: PostRow[] }) {
  const rows = useMemo(() => {
    const map = new Map<string, { posts: number; engagement: number | null }>();
    for (const post of posts) {
      if (!post.community_name) continue;
      const current = map.get(post.community_name) ?? { posts: 0, engagement: null };
      const value = engagementOf(post);
      map.set(post.community_name, {
        posts: current.posts + 1,
        engagement: value === null ? current.engagement : (current.engagement ?? 0) + value,
      });
    }
    return [...map.entries()].sort((a, b) => (b[1].engagement ?? -1) - (a[1].engagement ?? -1));
  }, [posts]);
  if (rows.length === 0) return <EmptyState title="Henüz topluluk kaydı yok">Link eklerken topluluk adını yazın.</EmptyState>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Topluluk</th>
            <th className="num">Paylaşım</th>
            <th className="num">Etkileşim</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, row]) => (
            <tr key={name}>
              <td className="font-semibold">{name}</td>
              <td className="num">{row.posts}</td>
              <td className="num">{formatCount(row.engagement)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Recommendations({ state }: { state: EngineState }) {
  const items: string[] = [];
  const flagged = state.people.filter((p) => p.status === "flagged");
  if (flagged.length > 0) items.push(`${flagged.map((p) => p.name).join(", ")} ile görüşün: uyarı sınırına ulaştı.`);
  const needLogin = [...new Set(state.posts.filter((p) => p.data_status === "AUTHORIZATION_REQUIRED").map((p) => p.platform))];
  if (needLogin.length > 0) items.push(`${needLogin.join(", ")} için Bağlantılar & ayarlar’dan oturum açın; bu linkler şu an ölçülemiyor.`);
  const fresh = state.communities.filter((c) => c.previous_posts === 0 && (c.relevance_score ?? 0) >= 60);
  if (fresh[0]) items.push(`${fresh[0].name} henüz hiç kullanılmadı ve oyununuzla yüksek eşleşiyor.`);
  const best = [...state.posts].sort((a, b) => (b.positive ?? -1) - (a.positive ?? -1))[0];
  if (best?.positive != null && best.sentiment_sample >= 5) {
    items.push(`${best.community_name ?? best.platform} paylaşımında olumlu tepki %${Math.round(best.positive * 100)}; benzer içerikle devam edin.`);
  }
  if (items.length === 0) return <EmptyState title="Şimdilik öneri yok">Veri biriktikçe burada sonraki adımlar görünür.</EmptyState>;
  return (
    <div className="grid gap-2.5">
      {items.map((text) => (
        <div key={text} className="recommendation">
          {text}
        </div>
      ))}
    </div>
  );
}

function ProviderList({ providers }: { providers: ProviderRow[] }) {
  if (providers.length === 0) return <EmptyState title="Henüz ölçüm yapılmadı">İlk ölçümden sonra platform durumları burada görünür.</EmptyState>;
  return (
    <div className="integration-list">
      {providers.map((p) => {
        const failing = p.last_failure_at !== null && (p.last_success_at === null || p.last_failure_at > p.last_success_at);
        const tone = p.paused ? "danger" : failing ? "warning" : "success";
        const label = p.paused ? "Duraklatıldı" : failing ? "Sorunlu" : "Sağlıklı";
        return (
          <div key={p.platform} className="integration-row">
            <span className={`connection-state ${tone}`} aria-hidden />
            <PlatformLogo platform={p.platform} size={24} />
            <div className="integration-copy">
              <strong>{p.platform}</strong>
              <small>
                {p.paused
                  ? "Bot koruması/hız sınırı görüldü; bir süre denenmeyecek"
                  : (p.last_error ?? (p.last_success_at ? `Son başarılı: ${timeAgo(p.last_success_at)}` : ""))}
              </small>
            </div>
            <Badge tone={tone}>{label}</Badge>
          </div>
        );
      })}
    </div>
  );
}
