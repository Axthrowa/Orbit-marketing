import { X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import {
  dataStatusView,
  errorMessage,
  formatCount,
  formatDate,
  formatDateTime,
  formatPercent,
  sentimentScore,
  shortUrl,
  unavailableMessage,
} from "../lib/format";
import { useAdmin } from "../state/AdminContext";
import { useEngine } from "../state/EngineContext";
import { CONTENT_LABEL } from "./AnalyticsScreen";
import type { CommentLabel, PostDetail, Snapshot, Tone } from "../types";
import { PlatformLogo } from "./PlatformLogo";
import { Alert, Badge, Button, Card, EmptyState, Field, SentimentBar } from "./ui";

type Filter = "ALL" | "POSITIVE" | "NEUTRAL" | "NEGATIVE";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "ALL", label: "Tümü" },
  { key: "POSITIVE", label: "Olumlu" },
  { key: "NEUTRAL", label: "Nötr" },
  { key: "NEGATIVE", label: "Olumsuz" },
];

const LABEL_VIEW: Record<CommentLabel, { tone: Tone; text: string }> = {
  POSITIVE: { tone: "success", text: "Olumlu" },
  NEUTRAL: { tone: "neutral", text: "Nötr" },
  NEGATIVE: { tone: "danger", text: "Olumsuz" },
  MIXED: { tone: "warning", text: "Karışık" },
  UNKNOWN: { tone: "neutral", text: "Belirsiz" },
};

export function PostDrawer({ postId, onClose }: { postId: number; onClose: () => void }) {
  const { engine, reload, toast } = useEngine();
  const [detail, setDetail] = useState<PostDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("ALL");

  const load = useCallback(async () => {
    try {
      setDetail(await engine.postDetail(postId));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [engine, postId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const comments = useMemo(() => {
    const all = detail?.comments ?? [];
    if (filter === "ALL") return all;
    return all.filter((c) => c.label === filter || (filter === "NEUTRAL" && c.label === "MIXED"));
  }, [detail, filter]);

  const afterChange = async () => {
    await load();
    await reload();
  };

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden />
      <aside className="drawer" role="dialog" aria-label="Gönderi ayrıntısı">
        <div className="card-head">
          <h2 className="card-title m-0">Paylaşım analizi</h2>
          <Button variant="ghost" small onClick={onClose} aria-label="Kapat">
            <X size={16} aria-hidden />
          </Button>
        </div>
        <div className="flex flex-col gap-4 px-4 pb-4">
          {error ? <Alert tone="danger">{error}</Alert> : null}
          {detail === null && !error ? <div className="muted p-4">Yükleniyor…</div> : null}
          {detail ? <Body detail={detail} comments={comments} filter={filter} setFilter={setFilter} onChanged={afterChange} toast={toast} /> : null}
          {detail ? <ArchiveAction postId={detail.post.id} onArchived={async () => { await reload(); onClose(); }} /> : null}
        </div>
      </aside>
    </>
  );
}

function Body({
  detail,
  comments,
  filter,
  setFilter,
  onChanged,
  toast,
}: {
  detail: PostDetail;
  comments: PostDetail["comments"];
  filter: Filter;
  setFilter: (filter: Filter) => void;
  onChanged: () => Promise<void>;
  toast: (tone: Tone, text: string) => void;
}) {
  const post = detail.post;
  const status = dataStatusView(post.data_status);
  const message = unavailableMessage(post.platform, post.data_status, post.last_metrics_at);
  const score = sentimentScore(post.positive, post.negative);
  return (
    <>
      <Card lift={false}>
        <div className="flex flex-wrap items-center gap-2">
          <PlatformLogo platform={post.platform} size={20} withName />
          <Badge tone={status.tone}>{status.label}</Badge>
          <span className="muted">
            {post.user_name} · {post.team_name ?? "Ekipsiz"}
          </span>
        </div>
        <div className="mono muted mt-2 break-all" title={post.url}>
          {shortUrl(post.url, 70)}
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1">
          <Row term="Topluluk" value={post.community_name ?? "—"} />
          <Row term="Paylaşım tarihi" value={formatDate(post.posted_at)} />
          <Row term="Son başarılı ölçüm" value={formatDateTime(post.last_metrics_at)} />
          <Row term="Son deneme" value={formatDateTime(post.last_attempt_at)} />
          <Row term="Kampanya" value={post.campaign_name ?? "—"} />
          <Row term="Oyun" value={post.game_name ?? "—"} />
          <Row term="İçerik türü" value={CONTENT_LABEL[post.content_type] ?? "—"} />
          <Row term="Veri kaynağı" value={post.last_source === "MANUAL" ? "Elle giriş" : post.last_source === "MOCK" ? "MOCK (sahte)" : post.last_source ? "Otomatik ölçüm" : "—"} />
        </dl>
        {post.preview_text ? <p className="muted mt-2 italic">“{post.preview_text}”</p> : null}
        {message ? (
          <div className="mt-3">
            <Alert tone="warning">{message}</Alert>
          </div>
        ) : null}
      </Card>

      <div className="post-stats">
        <Counter label="Beğeni" value={post.likes} />
        <Counter label="Yorum" value={post.comments} />
        <Counter label="Paylaşım" value={post.shares} />
        <Counter label="İzlenme" value={post.views} />
      </div>

      <Card lift={false} kicker="Etkileşimin yolculuğu" title="Zaman içindeki değişim">
        {detail.analytics ? (
          <dl className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1">
            <Row term="İlk 1 saatte hız" value={velocity(detail.analytics.velocity_1h)} />
            <Row term="İlk 6 saatte hız" value={velocity(detail.analytics.velocity_6h)} />
            <Row term="İlk 24 saatte hız" value={velocity(detail.analytics.velocity_24h)} />
            <Row term="Etkileşim oranı" value={formatPercent(detail.analytics.engagement_rate)} />
            <Row term="Beğeni artışı" value={growth(detail.analytics.likes_growth)} />
            <Row term="İzlenme artışı" value={growth(detail.analytics.views_growth)} />
          </dl>
        ) : null}
        <Sparklines snapshots={detail.snapshots} />
      </Card>

      <Card
        lift={false}
        kicker="Oyuncunun sesi"
        title="Oyuncu tepkisi"
        actions={score === null ? null : <Badge tone={score >= 0 ? "success" : "danger"}>Skor {score > 0 ? "+" : ""}{score}</Badge>}
      >
        <SentimentBar positive={post.positive} negative={post.negative} sample={post.sentiment_sample} />
        <div className="mt-3 flex gap-1.5" role="group" aria-label="Yorum filtresi">
          {FILTERS.map((item) => (
            <button key={item.key} className="chip" aria-pressed={filter === item.key} onClick={() => setFilter(item.key)}>
              {item.label}
            </button>
          ))}
        </div>
        {comments.length === 0 ? (
          <EmptyState title="Yorum yok">Otomatik toplanamadıysa aşağıdan elle yapıştırabilirsiniz.</EmptyState>
        ) : (
          <ul className="m-0 mt-2 flex list-none flex-col gap-2 p-0">
            {comments.map((comment, index) => {
              const view = LABEL_VIEW[comment.label];
              return (
                <li key={`${index}-${comment.text.slice(0, 12)}`} className="flex gap-2">
                  <Badge tone={view.tone}>{view.text}</Badge>
                  <span className="min-w-0 break-words">
                    {comment.text}
                    {comment.topics && comment.topics.length > 0 ? (
                      <small className="muted block">{comment.topics.map((key) => detail.topic_labels?.[key] ?? key).join(" · ")}</small>
                    ) : null}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <PageNote postId={post.id} initial={post.note} community={post.community_name} onChanged={onChanged} toast={toast} />
      <ManualMetrics postId={post.id} onChanged={onChanged} toast={toast} />
      <ManualComments postId={post.id} onChanged={onChanged} toast={toast} />
    </>
  );
}

function velocity(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value.toLocaleString("tr-TR")} / saat`;
}

function growth(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${formatCount(value)}`;
}

/** Yönetici: paylaşımı arşivler (silmez); arşivdekiler listelerden ve analitikten çıkar. */
function ArchiveAction({ postId, onArchived }: { postId: number; onArchived: () => Promise<void> }) {
  const { engine, toast } = useEngine();
  const admin = useAdmin();
  if (!admin.unlocked) return null;
  const archive = async () => {
    try {
      const done = await admin.run("Paylaşımı arşivlemek için yönetici doğrulaması gerekir", (pin) => engine.archivePost(pin, postId, true));
      if (done !== null) {
        toast("info", "Paylaşım arşivlendi; ölçüm geçmişi korunur");
        await onArchived();
      }
    } catch (caught) {
      toast("danger", errorMessage(caught));
    }
  };
  return (
    <div className="flex justify-end">
      <Button variant="danger" small onClick={() => void archive()}>
        Paylaşımı arşivle
      </Button>
    </div>
  );
}

function Row({ term, value }: { term: string; value: string }) {
  return (
    <>
      <dt className="muted">{term}</dt>
      <dd className="m-0 text-right">{value}</dd>
    </>
  );
}

function Counter({ label, value }: { label: string; value: number | null }) {
  return (
    <div title={value === null ? "Bilinmiyor (0 değil)" : undefined}>
      <span>{label}</span>
      <strong>{formatCount(value)}</strong>
    </div>
  );
}

function Sparklines({ snapshots }: { snapshots: Snapshot[] }) {
  const series: { key: "likes" | "comments" | "views"; label: string }[] = [
    { key: "likes", label: "Beğeni" },
    { key: "views", label: "İzlenme" },
    { key: "comments", label: "Yorum" },
  ];
  if (snapshots.length < 2) {
    return <div className="muted">Henüz yeterli ölçüm yok (grafik için en az 2 ölçüm gerekir).</div>;
  }
  return (
    <div className="flex flex-col gap-3">
      {series.map(({ key, label }) => {
        const points = snapshots.map((s) => s[key]).filter((v): v is number => v !== null);
        if (points.length < 2) return null;
        return <Sparkline key={key} label={label} values={points} />;
      })}
    </div>
  );
}

function Sparkline({ label, values }: { label: string; values: number[] }) {
  const width = 480;
  const height = 38;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const path = values
    .map((v, i) => `${(i / (values.length - 1)) * width},${height - 4 - ((v - min) / span) * (height - 8)}`)
    .join(" ");
  const first = values[0] ?? 0;
  const last = values[values.length - 1] ?? 0;
  return (
    <div>
      <div className="flex justify-between text-[11px]">
        <span className="muted">{label}</span>
        <span>
          {formatCount(first)} → <strong>{formatCount(last)}</strong>
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label={`${label} grafiği`}>
        <polyline points={path} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

function PageNote({
  postId,
  initial,
  community,
  onChanged,
  toast,
}: {
  postId: number;
  initial: string | null;
  community: string | null;
  onChanged: () => Promise<void>;
  toast: (tone: Tone, text: string) => void;
}) {
  const { engine } = useEngine();
  const [text, setText] = useState(initial ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await engine.updateNote(postId, text);
      toast("success", text.trim() ? "Sayfa notu kaydedildi" : "Sayfa notu silindi");
      await onChanged();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card lift={false} kicker="Paylaşanın notu" title="Sayfa hakkında not">
      <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-3">
        <Field
          label={community ? `${community} hakkında` : "Sayfa hakkında"}
          htmlFor="page-note"
          hint="Kurallar, üyelerin tepkisi, bir dahaki paylaşımda dikkat edilecekler. Bu topluluğu seçen herkes görür."
        >
          <textarea id="page-note" className="textarea" maxLength={500} value={text} onChange={(event) => setText(event.target.value)} />
        </Field>
        {error ? <Alert tone="danger">{error}</Alert> : null}
        <div>
          <Button type="submit" variant="primary" busy={busy} disabled={text === (initial ?? "")}>
            Notu kaydet
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ManualMetrics({
  postId,
  onChanged,
  toast,
}: {
  postId: number;
  onChanged: () => Promise<void>;
  toast: (tone: Tone, text: string) => void;
}) {
  const { engine } = useEngine();
  const [values, setValues] = useState({ likes: "", comments: "", shares: "", views: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await engine.manualMetrics({ postId, ...values });
      toast("success", "Elle girilen sayaçlar kaydedildi");
      setValues({ likes: "", comments: "", shares: "", views: "" });
      await onChanged();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const fields: { key: keyof typeof values; label: string }[] = [
    { key: "likes", label: "Beğeni" },
    { key: "comments", label: "Yorum" },
    { key: "shares", label: "Paylaşım" },
    { key: "views", label: "İzlenme" },
  ];

  return (
    <Card lift={false} kicker="Elle giriş" title="Elle sayaç gir">
      <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-3">
        <div className="muted">
          Otomatik ölçülemeyen bağlantılar (örn. kişisel Facebook/Instagram) için. Boş bırakılan alan “bilinmiyor” kalır.
        </div>
        <div className="grid grid-cols-4 gap-2">
          {fields.map(({ key, label }) => (
            <Field key={key} label={label} htmlFor={`m-${key}`}>
              <input
                id={`m-${key}`}
                className="input"
                inputMode="numeric"
                value={values[key]}
                onChange={(event) => setValues({ ...values, [key]: event.target.value })}
              />
            </Field>
          ))}
        </div>
        {error ? <Alert tone="danger">{error}</Alert> : null}
        <div>
          <Button type="submit" variant="primary" busy={busy}>
            Kaydet
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ManualComments({
  postId,
  onChanged,
  toast,
}: {
  postId: number;
  onChanged: () => Promise<void>;
  toast: (tone: Tone, text: string) => void;
}) {
  const { engine } = useEngine();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (lines.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const added = await engine.manualComments(postId, lines);
      toast("success", `${added} yeni yorum analiz edildi`);
      setText("");
      await onChanged();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card lift={false} kicker="Elle giriş" title="Yorumları elle yapıştır">
      <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-3">
        <Field label="Her satıra bir yorum" htmlFor="manual-comments" hint="Yazar bilgisi saklanmaz; @etiketler maskelenir.">
          <textarea id="manual-comments" className="textarea" value={text} onChange={(event) => setText(event.target.value)} />
        </Field>
        {error ? <Alert tone="danger">{error}</Alert> : null}
        <div>
          <Button type="submit" variant="primary" busy={busy} disabled={text.trim().length === 0}>
            Analiz et
          </Button>
        </div>
      </form>
    </Card>
  );
}
