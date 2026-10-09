import { useEffect, useMemo, useState } from "react";

import { errorMessage, formatCount, sentimentScore } from "../lib/format";
import { useEngine } from "../state/EngineContext";
import type { CommentLabel, CommentRow, TopicCount, Tone } from "../types";
import { TopicsCard } from "./AnalyticsScreen";
import { PlatformLogo } from "./PlatformLogo";
import { Alert, Badge, Card, EmptyState, SentimentBar } from "./ui";

type Filter = "ALL" | "POSITIVE" | "NEUTRAL" | "NEGATIVE";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "ALL", label: "Tüm yorumlar" },
  { key: "POSITIVE", label: "Olumlu" },
  { key: "NEUTRAL", label: "Nötr / karma" },
  { key: "NEGATIVE", label: "Olumsuz" },
];

export const LABEL_VIEW: Record<CommentLabel, { tone: Tone; text: string }> = {
  POSITIVE: { tone: "success", text: "Olumlu" },
  NEUTRAL: { tone: "neutral", text: "Nötr" },
  NEGATIVE: { tone: "danger", text: "Olumsuz" },
  MIXED: { tone: "warning", text: "Karma" },
  UNKNOWN: { tone: "neutral", text: "Belirsiz" },
};

export function AudienceScreen({ userId, teamId }: { userId: number | null; teamId: number | null }) {
  const { engine, state } = useEngine();
  const [topics, setTopics] = useState<TopicCount[]>([]);
  useEffect(() => {
    let alive = true;
    engine
      .analytics({ days: null, user_id: userId, team_id: teamId })
      .then((result) => {
        if (alive) setTopics(result.topics);
      })
      .catch(() => {
        if (alive) setTopics([]); // konu paneli isteğe bağlı; yorum listesi yine çalışır
      });
    return () => {
      alive = false;
    };
  }, [engine, userId, teamId, state?.generated_at]);
  const analysed = useMemo(
    () => (state?.posts ?? []).filter((p) => p.sentiment_sample > 0).sort((a, b) => b.sentiment_sample - a.sentiment_sample),
    [state],
  );
  const totals = useMemo(() => {
    let positive = 0;
    let negative = 0;
    let sample = 0;
    for (const post of analysed) {
      sample += post.sentiment_sample;
      positive += (post.positive ?? 0) * post.sentiment_sample;
      negative += (post.negative ?? 0) * post.sentiment_sample;
    }
    if (sample === 0) return null;
    return { positive: positive / sample, negative: negative / sample, neutral: Math.max(0, 1 - (positive + negative) / sample), sample };
  }, [analysed]);

  const [postId, setPostId] = useState<number | null>(null);
  const [comments, setComments] = useState<CommentRow[]>([]);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (postId === null && analysed[0]) setPostId(analysed[0].id);
  }, [analysed, postId]);

  useEffect(() => {
    if (postId === null) return;
    let cancelled = false;
    engine
      .postDetail(postId)
      .then((detail) => {
        if (!cancelled) {
          setComments(detail.comments);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught));
      });
    return () => {
      cancelled = true;
    };
  }, [engine, postId]);

  const visible = comments.filter((c) => filter === "ALL" || c.label === filter || (filter === "NEUTRAL" && c.label === "MIXED"));

  return (
    <div className="stack">
      <section className="panel sentiment-hero">
        <div>
          <span className="small-label">Sayıların ötesinde</span>
          <h2>Oyuncular ne hissediyor?</h2>
          <p className="muted">
            Olumlu, olumsuz ve nötr yorumları ayıran açıklanabilir Türkçe / İngilizce kural motoru. Spam ve boş yorumlar sayılmaz; beğeni sayısı
            olumlu görüş kabul edilmez.
          </p>
        </div>
        <div className="sentiment-totals">
          <div className="sentiment-total">
            <strong style={{ color: "var(--success)" }}>{totals ? `%${Math.round(totals.positive * 100)}` : "—"}</strong>
            <span>Olumlu</span>
          </div>
          <div className="sentiment-total">
            <strong>{totals ? `%${Math.round(totals.neutral * 100)}` : "—"}</strong>
            <span>Nötr / karma</span>
          </div>
          <div className="sentiment-total">
            <strong style={{ color: "var(--danger)" }}>{totals ? `%${Math.round(totals.negative * 100)}` : "—"}</strong>
            <span>Olumsuz</span>
          </div>
          <div className="sentiment-total">
            <strong>{formatCount(totals?.sample ?? null)}</strong>
            <span>Analiz edilen yorum</span>
          </div>
        </div>
      </section>

      <div className="analysis-grid">
        <Card kicker="Öne çıkan paylaşımlar" title="Paylaşım bazında tepki" flush>
          {analysed.length === 0 ? (
            <EmptyState title="Henüz analiz edilen yorum yok">Yorumlar toplandıkça ya da elle yapıştırıldıkça burada görünür.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Paylaşım</th>
                    <th className="num">Yorum</th>
                    <th style={{ width: 150 }}>Dağılım</th>
                    <th className="num">Skor</th>
                  </tr>
                </thead>
                <tbody>
                  {analysed.map((post) => {
                    const score = sentimentScore(post.positive, post.negative);
                    return (
                      <tr key={post.id} className="row-click" onClick={() => setPostId(post.id)} aria-selected={post.id === postId}>
                        <td>
                          <div className="flex items-center gap-2">
                            <PlatformLogo platform={post.platform} size={18} />
                            <strong className="text-[11px]">{post.community_name ?? "Topluluk yok"}</strong>
                          </div>
                          <small>{post.user_name}</small>
                        </td>
                        <td className="num">{post.sentiment_sample}</td>
                        <td>
                          <SentimentBar positive={post.positive} negative={post.negative} sample={post.sentiment_sample} />
                        </td>
                        <td className="num font-semibold" style={{ color: score === null ? undefined : score >= 0 ? "var(--success)" : "var(--danger)" }}>
                          {score === null ? "—" : `${score > 0 ? "+" : ""}${score}`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card
          kicker="Yorum defteri"
          title="Oyuncunun sesi"
          actions={
            <select className="select" style={{ width: "auto" }} aria-label="Yorum sınıfı" value={filter} onChange={(event) => setFilter(event.target.value as Filter)}>
              {FILTERS.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label}
                </option>
              ))}
            </select>
          }
        >
          {error ? <Alert tone="danger">{error}</Alert> : null}
          {visible.length === 0 ? (
            <EmptyState title="Bu filtrede yorum yok">Soldan başka bir paylaşım seçebilirsiniz.</EmptyState>
          ) : (
            <div className="grid gap-3">
              {visible.map((comment, index) => {
                const view = LABEL_VIEW[comment.label];
                return (
                  <blockquote key={`${index}-${comment.text.slice(0, 16)}`}>
                    {comment.text}
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <Badge tone={view.tone}>{view.text}</Badge>
                      <span className="muted text-[10px]">{comment.language === "tr" ? "Türkçe" : comment.language === "en" ? "İngilizce" : "Dil belirsiz"}</span>
                    </div>
                  </blockquote>
                );
              })}
            </div>
          )}
          <p className="form-help">Yazar bilgisi saklanmaz; @etiketler maskelenir. İroni ve bağlam her zaman doğru çözülemez.</p>
        </Card>
      </div>
      <TopicsCard topics={topics} />
    </div>
  );
}
