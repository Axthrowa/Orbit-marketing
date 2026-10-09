import { formatDate, recommendationView } from "../lib/format";
import type { Tone, PostingContext } from "../types";
import { Alert, Badge, Button } from "./ui";

const TITLES: Record<PostingContext["recommendation"], string> = {
  CLEAN: "Bu toplulukta henüz paylaşım yapılmadı (Temiz)",
  SAFE: "Son paylaşımın üzerinden yeterince zaman geçmiş",
  CAUTION: "Dikkat: bir süre önce paylaşım yapılmış",
  RECENTLY_USED: "Yakın zamanda kullanıldı",
  AVOID: "Çok yakın zamanda paylaşım yapılmış",
};

const TONES: Record<PostingContext["recommendation"], Tone> = {
  CLEAN: "success",
  SAFE: "success",
  CAUTION: "warning",
  RECENTLY_USED: "warning",
  AVOID: "danger",
};

export function CommunityHistoryCard({
  context,
  onFindOther,
}: {
  context: PostingContext;
  onFindOther?: () => void;
}) {
  const tone = TONES[context.recommendation];
  const view = recommendationView(context.recommendation);
  const last = context.last_post;
  return (
    <Alert
      tone={tone}
      title={
        <span className="flex flex-wrap items-center gap-2">
          {TITLES[context.recommendation]} <Badge tone={view.tone}>{view.label}</Badge>
        </span>
      }
      actions={
        context.recommendation !== "CLEAN" && context.recommendation !== "SAFE" && onFindOther ? (
          <Button small onClick={onFindOther}>
            Başka topluluk bul
          </Button>
        ) : null
      }
    >
      {last ? (
        <div className="flex flex-col gap-1">
          <div>
            <strong>Son paylaşım:</strong> {formatDate(last.posted_at)} ({context.days_since_last_post} gün önce) ·{" "}
            <strong>{last.user}</strong>
            {last.team ? ` (${last.team})` : ""}
          </div>
          {last.preview ? (
            <div className="italic">
              Önizleme: “{last.preview}
              {last.preview.length >= 150 ? "…" : ""}”
            </div>
          ) : (
            <div className="muted">Önizleme metni kaydedilmemiş.</div>
          )}
          <div className="muted">Bu toplulukta toplam {context.previous_posts} paylaşım kaydı var.</div>
          {context.recent_posts.some((entry) => entry.note) ? (
            <div className="mt-1 grid gap-2">
              <strong className="text-[11px]">Ekibin bu sayfa hakkındaki notları</strong>
              {context.recent_posts
                .filter((entry) => entry.note)
                .map((entry) => (
                  <div key={`note-${entry.posted_at}-${entry.url}`} className="note-block">
                    {entry.note}
                    <small>
                      {entry.user} · {formatDate(entry.posted_at)}
                    </small>
                  </div>
                ))}
            </div>
          ) : null}
          {context.recent_posts.length > 1 ? (
            <details>
              <summary className="cursor-pointer muted">Önceki paylaşımlar</summary>
              <ul className="m-0 mt-1 list-none p-0">
                {context.recent_posts.slice(1).map((entry) => (
                  <li key={`${entry.posted_at}-${entry.url}`} className="muted">
                    {formatDate(entry.posted_at)} · {entry.user}
                    {entry.preview ? ` — “${entry.preview.slice(0, 60)}${entry.preview.length > 60 ? "…" : ""}”` : ""}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}
    </Alert>
  );
}
