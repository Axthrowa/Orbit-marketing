import { Copy, Play } from "lucide-react";
import { useState } from "react";

import { dataStatusView, formatCount, formatDate, shortUrl, timeAgo, unavailableMessage } from "../lib/format";
import { useEngine } from "../state/EngineContext";
import type { PostRow } from "../types";
import { PlatformLogo } from "./PlatformLogo";
import { Avatar, Badge, Button, EmptyState, SentimentBar } from "./ui";

interface Props {
  posts: PostRow[];
  onOpen: (postId: number) => void;
}

export function MetricsTable({ posts, onOpen }: Props) {
  const { engine, reload, toast } = useEngine();
  const [busyId, setBusyId] = useState<number | null>(null);

  if (posts.length === 0) {
    return <EmptyState title="Gösterilecek paylaşım yok">Yukarıdan ilk linki ekleyin; ölçümler otomatik başlar.</EmptyState>;
  }

  const measure = async (post: PostRow) => {
    setBusyId(post.id);
    try {
      const summary = await engine.refresh([post.id]);
      if (summary.ok > 0) toast("success", "Ölçüm güncellendi");
      else if (summary.skipped_paused > 0)
        toast("warning", `${post.platform} geçici olarak duraklatıldı (bot koruması/hız sınırı görüldü)`);
      else toast("warning", unavailableText(post) ?? "Veri alınamadı");
    } catch (caught) {
      toast("danger", caught instanceof Error ? caught.message : "Ölçüm başarısız");
    } finally {
      setBusyId(null);
      await reload();
    }
  };

  return (
    <div className="table-wrap" style={{ maxHeight: 650 }}>
      <table style={{ minWidth: 980 }}>
        <thead>
          <tr>
            <th>Kişi / tarih</th>
            <th>Paylaşım</th>
            <th className="num">Beğeni</th>
            <th className="num">Yorum</th>
            <th className="num">Paylaşım</th>
            <th className="num">İzlenme</th>
            <th style={{ width: 130 }}>Oyuncu tepkisi</th>
            <th>Veri durumu</th>
            <th aria-label="İşlemler" />
          </tr>
        </thead>
        <tbody>
          {posts.map((post) => {
            const status = dataStatusView(post.data_status);
            const message = unavailableText(post);
            return (
              <tr key={post.id} className="row-click" onClick={() => onOpen(post.id)}>
                <td>
                  <span className="person-cell">
                    <Avatar name={post.user_name} />
                    <span>
                      {post.user_name}
                      <small>
                        {formatDate(post.posted_at)} · {post.team_name ?? "Ekipsiz"}
                      </small>
                    </span>
                  </span>
                </td>
                <td>
                  <div className="flex items-center gap-2">
                    <PlatformLogo platform={post.platform} size={18} />
                    <span className="post-link" title={post.url}>
                      {shortUrl(post.url, 32)}
                    </span>
                  </div>
                  <small>{post.community_name ?? "Topluluk belirtilmedi"}</small>
                  {post.note ? (
                    <small className="max-w-[260px] truncate" title={post.note}>
                      Not: {post.note}
                    </small>
                  ) : null}
                </td>
                <td className="num">{formatCount(post.likes)}</td>
                <td className="num">{formatCount(post.comments)}</td>
                <td className="num">{formatCount(post.shares)}</td>
                <td className="num">{formatCount(post.views)}</td>
                <td>
                  <SentimentBar positive={post.positive} negative={post.negative} sample={post.sentiment_sample} />
                </td>
                <td>
                  <div className="tracking-detail">
                    <Badge tone={status.tone} title={message ?? post.last_error ?? undefined}>
                      {status.label}
                    </Badge>
                    <div className="mt-1" title={message ?? undefined}>
                      {post.last_metrics_at ? `Son başarılı: ${timeAgo(post.last_metrics_at)}` : "Henüz ölçülmedi"}
                    </div>
                  </div>
                </td>
                <td onClick={(event) => event.stopPropagation()}>
                  <div className="flex gap-1">
                    <Button small variant="ghost" aria-label={`${post.user_name} gönderisini şimdi ölç`} title="Şimdi ölç" busy={busyId === post.id} onClick={() => void measure(post)}>
                      <Play size={13} aria-hidden />
                    </Button>
                    <Button
                      small
                      variant="ghost"
                      aria-label="Bağlantıyı kopyala"
                      title="Bağlantıyı kopyala"
                      onClick={() => {
                        navigator.clipboard.writeText(post.url).then(
                          () => toast("info", "Bağlantı kopyalandı"),
                          () => toast("warning", `Kopyalanamadı; bağlantı: ${post.url}`),
                        );
                      }}
                    >
                      <Copy size={13} aria-hidden />
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function unavailableText(post: PostRow): string | null {
  return unavailableMessage(post.platform, post.data_status, post.last_metrics_at);
}
