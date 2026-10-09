import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { errorMessage } from "../lib/format";
import { guessPlatform } from "../lib/platforms";
import { useEngine } from "../state/EngineContext";
import type { ContentType, PostingContext } from "../types";
import { CONTENT_LABEL } from "./AnalyticsScreen";
import { CommunityHistoryCard } from "./CommunityHistoryCard";
import { MetricsTable } from "./MetricsTable";
import { PlatformLogo } from "./PlatformLogo";
import { PostDrawer } from "./PostDrawer";
import { Alert, Button, Card, Field } from "./ui";

const LOOKUP_DELAY_MS = 350;

export interface Prefill {
  communityName?: string;
  /** Genel aramadan gelen paylaşım: ayrıntı çekmecesi açılır. */
  openPostId?: number;
  /** Değişikliğin yeniden uygulanması için her ön doldurmada artar. */
  nonce?: number;
}

/** Paylaşımlar ekranı: link ekleme (Orbit "Tek link. Tek adım.") + paylaşım arşivi. */
export function AddLinkForm({
  prefill,
  accountId,
  onFindCommunity,
}: {
  prefill?: Prefill;
  /** Kullanıcı hesabında paylaşan kişi sabittir; yönetici hesabında (null) kişi seçilir. */
  accountId: number | null;
  onFindCommunity: () => void;
}) {
  const { engine, state, reload, toast } = useEngine();
  const people = useMemo(() => (state?.people ?? []).filter((p) => p.status !== "inactive"), [state]);
  const [userId, setUserId] = useState<string>("");
  const [url, setUrl] = useState("");
  const [community, setCommunity] = useState(prefill?.communityName ?? "");
  const [preview, setPreview] = useState("");
  const [note, setNote] = useState("");
  const [postedAt, setPostedAt] = useState("");
  const [context, setContext] = useState<PostingContext | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openPost, setOpenPost] = useState<number | null>(null);
  const [personFilter, setPersonFilter] = useState("");
  const [search, setSearch] = useState("");
  const [campaignId, setCampaignId] = useState<string>("");
  const [contentType, setContentType] = useState<ContentType>("post");
  const [campaignFilter, setCampaignFilter] = useState("");
  const activeCampaigns = (state?.campaigns ?? []).filter((c) => c.status === "active" || c.status === "planned");
  const account = state?.accounts.find((a) => a.id === accountId) ?? null;
  const readOnly = account?.role === "viewer";

  useEffect(() => {
    if (prefill?.openPostId !== undefined) setOpenPost(prefill.openPostId);
  }, [prefill?.openPostId, prefill?.nonce]);

  useEffect(() => {
    if (prefill?.communityName) setCommunity(prefill.communityName);
  }, [prefill?.communityName]);

  useEffect(() => {
    if (accountId !== null) setUserId(String(accountId));
    else if (userId === "" && people[0]) setUserId(String(people[0].id));
  }, [accountId, people, userId]);

  // Topluluk adı yazıldıkça geçmişi sorgula (yakın zamanlı/mükerrer paylaşım uyarısı).
  const selectedTeam = people.find((p) => String(p.id) === userId)?.team_id ?? null;
  useEffect(() => {
    const name = community.trim();
    if (name.length < 2) {
      setContext(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      engine
        .postingContext({ name, teamId: selectedTeam })
        .then((result) => {
          if (!cancelled) setContext(result);
        })
        .catch(() => {
          if (!cancelled) setContext(null);
        });
    }, LOOKUP_DELAY_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [community, engine, selectedTeam]);

  const detected = url.trim() ? guessPlatform(url) : null;
  const warned = context !== null && context.recommendation !== "CLEAN" && context.recommendation !== "SAFE";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (userId === "") return setError("Önce Ekip yönetimi ekranından bir kişi ekleyin");
    setBusy(true);
    try {
      const result = await engine.addPost({
        user_id: Number(userId),
        url: url.trim(),
        community_name: community.trim() || undefined,
        preview_text: preview.trim() || undefined,
        note: note.trim() || undefined,
        posted_at: postedAt || undefined,
        campaign_id: campaignId === "" ? undefined : Number(campaignId),
        content_type: contentType,
      });
      if (!result.created) {
        toast("warning", "Bu bağlantı bu kişi için zaten kayıtlı");
      } else {
        toast("success", `${result.platform} paylaşımı kaydedildi; ilk ölçüm başlatıldı`);
        setUrl("");
        setPreview("");
        setNote("");
        setPostedAt("");
        void engine.refresh([result.post_id]).then(reload).catch(() => undefined);
      }
      await reload();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const knownCommunities = (state?.communities ?? []).filter((c) => c.status !== "blocked");
  const posts = (state?.posts ?? []).filter((p) => {
    if (personFilter !== "" && String(p.user_id) !== personFilter) return false;
    if (campaignFilter !== "" && String(p.campaign_id ?? "") !== campaignFilter) return false;
    const query = search.trim().toLocaleLowerCase("tr-TR");
    if (!query) return true;
    return [p.platform, p.url, p.community_name ?? "", p.user_name, p.note ?? ""].some((value) => value.toLocaleLowerCase("tr-TR").includes(query));
  });

  return (
    <div className="stack">
      {readOnly ? (
        <Alert tone="info" title="İzleyici hesabı (salt okunur)">
          Bu hesap paylaşımları ve istatistikleri görebilir, yeni link ekleyemez.
        </Alert>
      ) : (
      <Card kicker="Tek link. Tek adım." title="Linki yapıştır. Takibi başlatalım." icon="arrow">
        <form onSubmit={(event) => void submit(event)}>
          <div className="link-entry">
            <Field label="Paylaşım linki" htmlFor="url">
              <input id="url" className="input" type="url" required placeholder="Gönderi veya video linkini buraya yapıştır…" value={url} onChange={(event) => setUrl(event.target.value)} />
            </Field>
            <Button type="submit" variant={warned ? "warning" : "primary"} icon="shares" busy={busy} disabled={url.trim() === ""}>
              {warned ? "Yine de kaydet" : "Takibi başlat"}
            </Button>
          </div>
          {detected ? (
            <div className="link-detect" aria-live="polite">
              <PlatformLogo platform={detected} size={16} withName />
              <span>bağlantısı tanındı</span>
            </div>
          ) : null}
          <div className="quick-flow" aria-label="Otomatik takip adımları">
            <span>Linki tanı</span>
            <span>Topluluk geçmişini kontrol et</span>
            <span>Etkileşimi düzenli ölç</span>
            <span>Yorumları analiz et</span>
          </div>
          <div className="submission-options" style={{ paddingTop: 0 }}>
            {accountId !== null ? (
              <Field label="Paylaşan kişi" htmlFor="user" hint="Kullanıcı hesabından alınır.">
                <input id="user" className="input" readOnly value={people.find((p) => p.id === accountId)?.name ?? ""} />
              </Field>
            ) : (
              <Field label="Paylaşan kişi" htmlFor="user">
                <select id="user" className="select" value={userId} onChange={(event) => setUserId(event.target.value)}>
                  {people.length === 0 ? <option value="">Kişi yok</option> : null}
                  {people.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                      {p.team_name ? ` · ${p.team_name}` : ""}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            <Field label="Paylaşılan topluluk" htmlFor="community">
              <input id="community" className="input" list="known-communities" placeholder="örn. r/IndieGaming" value={community} onChange={(event) => setCommunity(event.target.value)} />
              <datalist id="known-communities">
                {knownCommunities.map((c) => (
                  <option key={c.id} value={c.name} />
                ))}
              </datalist>
            </Field>
          </div>

          <div className="submission-options" style={{ paddingTop: 0 }}>
            <Field label="Kampanya" htmlFor="campaign" hint="Oyun kampanyadan alınır; analitik buna göre süzülür.">
              <select id="campaign" className="select" value={campaignId} onChange={(event) => setCampaignId(event.target.value)}>
                <option value="">Kampanyasız</option>
                {activeCampaigns.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.game_name ? ` · ${c.game_name}` : ""}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="İçerik türü" htmlFor="content-type">
              <select id="content-type" className="select" value={contentType} onChange={(event) => setContentType(event.target.value as ContentType)}>
                {(Object.keys(CONTENT_LABEL) as ContentType[]).map((key) => (
                  <option key={key} value={key}>
                    {CONTENT_LABEL[key]}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <div className="mt-3.5">
            <Field
              label="Sayfa hakkında not"
              htmlFor="note"
              hint="Topluluğun kuralları, üyelerin tepkisi, bir dahaki paylaşımda dikkat edilecekler… Bu topluluğu seçen herkes notunu görür."
            >
              <textarea id="note" className="textarea" maxLength={500} placeholder="Örn. Moderatörler doğrudan Steam linkini siliyor; görselle paylaşınca daha çok yorum geliyor." value={note} onChange={(event) => setNote(event.target.value)} />
            </Field>
          </div>

          {context ? (
            <div className="mt-4">
              <CommunityHistoryCard context={context} onFindOther={onFindCommunity} />
            </div>
          ) : null}

          <details className="submission-advanced">
            <summary>İsteğe bağlı ayrıntılar · paylaşım metni, eski tarih</summary>
            <div className="submission-options">
              <Field label="Paylaşım metni" htmlFor="preview" hint="İlk 150 karakteri topluluk geçmişinde önizleme olarak gösterilir.">
                <textarea id="preview" className="textarea" value={preview} onChange={(event) => setPreview(event.target.value)} />
              </Field>
              <Field label="Gerçek paylaşım tarihi" htmlFor="posted" hint="Boş bırakılırsa bugün.">
                <input id="posted" className="input" type="date" value={postedAt} max={new Date().toISOString().slice(0, 10)} onChange={(event) => setPostedAt(event.target.value)} />
              </Field>
            </div>
          </details>

          <p className="form-help">
            Platform bağlantıdan tanınır. Veri alınamayan platformlarda link saklanır, sayılar tahmin edilmez; ayrıntıdan elle girilebilir.
          </p>
          {error ? (
            <div className="mt-3">
              <Alert tone="danger">{error}</Alert>
            </div>
          ) : null}
        </form>
      </Card>
      )}

      <Card kicker="Paylaşım arşivi" title="Her linkin etkisi" actions={<span className="muted text-[11px]">{posts.length} paylaşım</span>} flush>
        <div className="filters">
          {accountId === null ? (
          <select aria-label="Kişiye göre filtrele" value={personFilter} onChange={(event) => setPersonFilter(event.target.value)}>
            <option value="">Tüm kişiler</option>
            {(state?.people ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          ) : null}
          <select aria-label="Kampanyaya göre filtrele" value={campaignFilter} onChange={(event) => setCampaignFilter(event.target.value)}>
            <option value="">Tüm kampanyalar</option>
            {(state?.campaigns ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <input type="search" placeholder="Platform, topluluk veya bağlantı ara" aria-label="Paylaşım ara" value={search} onChange={(event) => setSearch(event.target.value)} />
        </div>
        <MetricsTable posts={posts} onOpen={setOpenPost} />
      </Card>

      {openPost !== null ? <PostDrawer postId={openPost} onClose={() => setOpenPost(null)} /> : null}
    </div>
  );
}
