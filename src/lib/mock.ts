// YALNIZCA tarayıcı önizlemesi ve testler için. Tauri içinde asla kullanılmaz; arayüz
// bu modda "DEMO VERİSİ" şeridi gösterir. Gerçek motor sözleşmesinin küçük bir taklidir.
import type { EngineTransport } from "./engine";
import type {
  AnalyticsOverview,
  BreakdownRow,
  Campaign,
  CommentRow,
  Game,
  InboxItem,
  LeaderboardRow,
  RecommendationItem,
  CommunityRow,
  EngineState,
  NotificationRow,
  PersonRow,
  PostRow,
  PostingContext,
  SettingSpec,
  SettingValue,
  Snapshot,
} from "../types";

export const PREVIEW_PIN = "123456";

const SPEC: SettingSpec[] = [
  { key: "inactivity_days", kind: "int", label: "Hareketsizlik eşiği (gün)", default: 3, low: 1, high: 60, choices: [], team_overridable: true },
  { key: "strike_interval_hours", kind: "int", label: "Uyarılar arası süre (saat)", default: 24, low: 1, high: 168, choices: [], team_overridable: true },
  { key: "max_strikes", kind: "int", label: "İşaretlenmeden önce uyarı sayısı", default: 3, low: 1, high: 10, choices: [], team_overridable: true },
  { key: "strike_check_time", kind: "time", label: "Günlük kontrol saati (HH:MM)", default: "00:00", low: 0, high: 0, choices: [], team_overridable: false },
  { key: "metrics_interval_hours", kind: "int", label: "Ölçüm aralığı (saat)", default: 6, low: 1, high: 168, choices: [], team_overridable: false },
  { key: "comment_limit", kind: "int", label: "Gönderi başına yorum sınırı", default: 50, low: 5, high: 500, choices: [], team_overridable: false },
  { key: "community_avoid_days", kind: "int", label: "Topluluk: KAÇIN (≤ gün)", default: 3, low: 0, high: 365, choices: [], team_overridable: false },
  { key: "community_recent_days", kind: "int", label: "Topluluk: YAKIN ZAMANDA (≤ gün)", default: 7, low: 0, high: 365, choices: [], team_overridable: false },
  { key: "community_caution_days", kind: "int", label: "Topluluk: DİKKAT (≤ gün)", default: 14, low: 0, high: 365, choices: [], team_overridable: false },
  { key: "scrape_enabled", kind: "bool", label: "Tarayıcı ile ölçüm açık", default: true, low: 0, high: 0, choices: [], team_overridable: false },
  { key: "scrape_headless", kind: "bool", label: "Tarayıcı arka planda çalışsın", default: true, low: 0, high: 0, choices: [], team_overridable: false },
  { key: "discovery_enabled", kind: "bool", label: "Topluluk keşfi açık", default: true, low: 0, high: 0, choices: [], team_overridable: false },
  { key: "discovery_interval_hours", kind: "int", label: "Keşif aralığı (saat)", default: 24, low: 1, high: 720, choices: [], team_overridable: false },
  { key: "discovery_keywords", kind: "list", label: "Keşif anahtar kelimeleri", default: ["FPS oyunları", "Indie Games"], low: 0, high: 0, choices: [], team_overridable: false },
  { key: "sentiment_engine", kind: "enum", label: "Duygu analizi motoru", default: "lexicon", low: 0, high: 0, choices: ["lexicon", "transformer"], team_overridable: false },
  { key: "notifications_enabled", kind: "bool", label: "Telegram bildirimleri açık", default: false, low: 0, high: 0, choices: [], team_overridable: false },
  { key: "admin_chat_id", kind: "str", label: "Yönetici Telegram sohbet kimliği", default: "", low: 0, high: 0, choices: [], team_overridable: false },
  { key: "email_enabled", kind: "bool", label: "E-posta bildirimleri açık", default: false, low: 0, high: 0, choices: [], team_overridable: false },
  { key: "smtp_host", kind: "str", label: "SMTP sunucusu (örn. smtp.gmail.com)", default: "", low: 0, high: 0, choices: [], team_overridable: false },
  { key: "smtp_port", kind: "int", label: "SMTP portu (465 SSL, 587 STARTTLS)", default: 587, low: 1, high: 65535, choices: [], team_overridable: false },
  { key: "smtp_user", kind: "str", label: "SMTP kullanıcı adı", default: "", low: 0, high: 0, choices: [], team_overridable: false },
  { key: "smtp_from", kind: "str", label: "Gönderen e-posta adresi", default: "", low: 0, high: 0, choices: [], team_overridable: false },
  { key: "admin_email", kind: "str", label: "Yönetici e-posta adresi", default: "", low: 0, high: 0, choices: [], team_overridable: false },
  { key: "teams_enabled", kind: "bool", label: "Microsoft Teams bildirimleri açık", default: false, low: 0, high: 0, choices: [], team_overridable: false },
  { key: "comment_retention_days", kind: "int", label: "Yorum metni saklama süresi (gün, 0 = süresiz)", default: 180, low: 0, high: 3650, choices: [], team_overridable: false },
  { key: "audit_retention_days", kind: "int", label: "Denetim günlüğü saklama süresi (gün, 0 = süresiz)", default: 365, low: 0, high: 3650, choices: [], team_overridable: false },
  { key: "backup_keep", kind: "int", label: "Tutulacak günlük yedek sayısı", default: 14, low: 1, high: 365, choices: [], team_overridable: false },
  { key: "metrics_schedule", kind: "enum", label: "Ölçüm takvimi (sabit / uyarlanabilir)", default: "fixed", low: 0, high: 0, choices: ["fixed", "adaptive"], team_overridable: false },
  { key: "target_languages", kind: "list", label: "Hedef kitle dilleri (tr, en, …)", default: ["tr", "en"], low: 0, high: 0, choices: [], team_overridable: false },
  { key: "perf_weight_consistency", kind: "int", label: "Performans ağırlığı: düzenli paylaşım", default: 20, low: 0, high: 100, choices: [], team_overridable: false },
  { key: "perf_weight_engagement", kind: "int", label: "Performans ağırlığı: etkileşim", default: 30, low: 0, high: 100, choices: [], team_overridable: false },
  { key: "perf_weight_sentiment", kind: "int", label: "Performans ağırlığı: oyuncu tepkisi", default: 15, low: 0, high: 100, choices: [], team_overridable: false },
  { key: "perf_weight_diversity", kind: "int", label: "Performans ağırlığı: topluluk çeşitliliği", default: 10, low: 0, high: 100, choices: [], team_overridable: false },
  { key: "perf_weight_velocity", kind: "int", label: "Performans ağırlığı: etkileşim hızı", default: 15, low: 0, high: 100, choices: [], team_overridable: false },
  { key: "perf_weight_campaign", kind: "int", label: "Performans ağırlığı: kampanya katkısı", default: 10, low: 0, high: 100, choices: [], team_overridable: false },
];

const HOUR = 3_600_000;
const ago = (ms: number): string => new Date(Date.now() - ms).toISOString().replace(/\.\d{3}Z$/, "Z");

class Failure extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export function createMockTransport(): EngineTransport {
  const values: Record<string, SettingValue> = Object.fromEntries(SPEC.map((s) => [s.key, s.default as SettingValue]));
  const teamOverrides = new Map<number, Record<string, SettingValue>>();
  let pinSet = true;
  let pin = PREVIEW_PIN;
  let nextId = 100;
  const secretState: Record<string, boolean> = { telegram_bot_token: false, smtp_password: false, teams_webhook: false };

  const teams = [
    { id: 1, name: "Marketing A", chat_id: "-100200", members: 2, flagged: 1 },
    { id: 2, name: "Marketing B", chat_id: null as string | null, members: 2, flagged: 0 },
  ];

  const person = (p: Partial<PersonRow> & Pick<PersonRow, "id" | "name" | "team_id" | "team_name">): PersonRow => ({
    role: "member",
    has_telegram: true,
    strike_count: 0,
    total_strikes: 0,
    max_strikes: 3,
    inactivity_days: 3,
    status: "active",
    last_post_at: ago(HOUR * 20),
    flagged_at: null,
    posts: 0,
    likes: null,
    comments: null,
    shares: null,
    views: null,
    engagement: null,
    days_since_last_post: 0,
    ...p,
  });

  const people: PersonRow[] = [
    person({ id: 1, name: "Ayşe Demir", team_id: 1, team_name: "Marketing A", posts: 3, likes: 321, comments: 37, shares: 14, views: 6800, engagement: 372 }),
    person({ id: 2, name: "Burak Yıldız", team_id: 1, team_name: "Marketing A", strike_count: 3, total_strikes: 3, status: "flagged", flagged_at: ago(HOUR * 5), last_post_at: ago(HOUR * 24 * 6), days_since_last_post: 6, posts: 1, has_telegram: true }),
    person({ id: 3, name: "Cem Kaya", team_id: 2, team_name: "Marketing B", strike_count: 1, total_strikes: 1, last_post_at: ago(HOUR * 24 * 3.2), days_since_last_post: 3, posts: 2, likes: 40, comments: 5, shares: null, views: null, engagement: 45 }),
    person({ id: 4, name: "Deniz Acar", team_id: 2, team_name: "Marketing B", role: "manager", has_telegram: false, last_post_at: null, days_since_last_post: null, posts: 0 }),
  ];

  const post = (p: Partial<PostRow> & Pick<PostRow, "id" | "platform" | "url" | "user_id" | "user_name" | "team_name">): PostRow => ({
    likes: null,
    comments: null,
    shares: null,
    views: null,
    initial_likes: null,
    positive: null,
    negative: null,
    sentiment_sample: 0,
    data_status: "PENDING",
    last_error: null,
    last_metrics_at: null,
    last_attempt_at: null,
    posted_at: ago(HOUR * 30),
    preview_text: null,
    note: null,
    community_name: null,
    content_type: "post",
    game_id: 1,
    campaign_id: 1,
    game_name: "Project Nova",
    campaign_name: "Nova Beta Duyurusu",
    last_source: "SCRAPE",
    ...p,
  });

  const posts: PostRow[] = [
    post({ id: 1, platform: "X", url: "https://x.com/axt/status/1840000000000000001", user_id: 1, user_name: "Ayşe Demir", team_name: "Marketing A", community_name: "r/IndieGaming", likes: 150, comments: 22, shares: 14, views: 6800, positive: 0.61, negative: 0.14, sentiment_sample: 28, data_status: "OK", last_metrics_at: ago(HOUR * 1.5), last_attempt_at: ago(HOUR * 1.5), preview_text: "After three years of development, our extraction shooter is finally playable", note: "Moderatörler doğrudan Steam linkini siliyor; oynanış videosuyla paylaşınca daha çok yorum geldi." }),
    post({ id: 2, platform: "Instagram", url: "https://www.instagram.com/p/DemoAbC123/", user_id: 1, user_name: "Ayşe Demir", team_name: "Marketing A", community_name: "FPS Türkiye", data_status: "AUTHORIZATION_REQUIRED", last_attempt_at: ago(HOUR * 2), last_error: "Instagram giriş istiyor" }),
    post({ id: 3, platform: "Facebook", url: "https://www.facebook.com/groups/oyuncular/posts/998877", user_id: 3, user_name: "Cem Kaya", team_name: "Marketing B", community_name: "Oyuncular Grubu", note: "Grup yöneticisi haftada bir tanıtıma izin veriyor (cuma).", likes: 40, comments: 5, data_status: "MANUAL", last_source: "MANUAL", content_type: "image", game_id: 2, game_name: "Skyforge Tales", campaign_id: 3, campaign_name: "Skyforge Kickstarter", last_metrics_at: ago(HOUR * 9), positive: 0.5, negative: 0.1, sentiment_sample: 4 }),
    post({ id: 4, platform: "Reddit", url: "https://www.reddit.com/r/IndieGaming/comments/abc123/demo/", user_id: 1, user_name: "Ayşe Demir", team_name: "Marketing A", community_name: "r/IndieGaming", content_type: "video", likes: 321, comments: 18, views: null, positive: 0.72, negative: 0.06, sentiment_sample: 18, data_status: "OK", last_metrics_at: ago(HOUR * 3), last_attempt_at: ago(HOUR * 3) }),
    post({ id: 5, platform: "Threads", url: "https://www.threads.net/@axt/post/DemoXyZ", user_id: 3, user_name: "Cem Kaya", team_name: "Marketing B", data_status: "DATA_UNAVAILABLE", last_metrics_at: ago(HOUR * 8), last_attempt_at: ago(HOUR * 1), likes: 12, last_error: "Bot koruması/hız sınırı görüldü" }),
    post({ id: 6, platform: "YouTube", url: "https://youtu.be/dQw4w9WgXcQ", user_id: 2, user_name: "Burak Yıldız", team_name: "Marketing A", posted_at: ago(HOUR * 24 * 6), data_status: "PENDING" }),
  ];

  const communities: CommunityRow[] = [
    { id: 1, name: "r/IndieGaming", platform: "Reddit", url: "https://www.reddit.com/r/IndieGaming/", category: null, member_count: 3_400_000, status: "approved", favorite: 1, relevance_score: 88, activity_score: 1, reason: "Anahtar kelime eşleşmesi %80, 3.400.000 üye", discovered_at: ago(HOUR * 100), last_used: ago(HOUR * 24 * 4), previous_posts: 2 },
    { id: 2, name: "r/FPS_Games", platform: "Reddit", url: "https://www.reddit.com/r/FPS_Games/", category: null, member_count: 250_000, status: "discovered", favorite: 0, relevance_score: 74, activity_score: 0.9, reason: "Anahtar kelime eşleşmesi %67, 250.000 üye", discovered_at: ago(HOUR * 50), last_used: null, previous_posts: 0 },
    { id: 3, name: "r/ExtractionShooter", platform: "Reddit", url: "https://www.reddit.com/r/ExtractionShooter/", category: null, member_count: null, status: "discovered", favorite: 0, relevance_score: 61, activity_score: 0, reason: "Anahtar kelime eşleşmesi %50, üye sayısı bilinmiyor", discovered_at: ago(HOUR * 20), last_used: null, previous_posts: 0 },
  ];

  const comments: CommentRow[] = [
    { text: "Harika görünüyor, wishlist'e ekledim!", language: "tr", label: "POSITIVE", positive: 0.7, negative: 0 },
    { text: "Fiyatı ne kadar olacak?", language: "tr", label: "NEUTRAL", positive: 0.1, negative: 0.05 },
    { text: "Bug dolu görünüyor, berbat optimizasyon", language: "tr", label: "NEGATIVE", positive: 0, negative: 0.7 },
    { text: "Can't wait to play this", language: "en", label: "POSITIVE", positive: 0.7, negative: 0 },
  ];
  const snapshots: Snapshot[] = [20, 60, 95, 130, 150].map((likes, i) => ({
    likes,
    comments: 4 + i * 4,
    shares: i * 3,
    views: 900 + i * 1400,
    source: "SCRAPE" as const,
    captured_at: ago(HOUR * (24 - i * 6)),
  }));

  const games: Game[] = [
    { id: 1, name: "Project Nova", genres: ["FPS", "Extraction Shooter"], keywords: ["pvpve"], languages: ["en", "tr"], website: null, steam_url: "https://store.steampowered.com/app/000000", status: "active", posts: 4 },
    { id: 2, name: "Skyforge Tales", genres: ["RPG", "Açık dünya"], keywords: ["fantasy"], languages: ["tr"], website: null, steam_url: null, status: "active", posts: 1 },
    { id: 3, name: "Pixel Racers", genres: ["Yarış"], keywords: ["retro"], languages: ["en"], website: null, steam_url: null, status: "archived", posts: 0 },
  ];
  const campaigns: Campaign[] = [
    { id: 1, name: "Nova Beta Duyurusu", game_id: 1, game_name: "Project Nova", description: "Kapalı beta kayıtları", start_date: "2026-09-20", end_date: "2026-10-31", status: "active", keywords: ["beta"], target_platforms: ["X", "Reddit"], posts: 4, engagement: 525, views: 6800 },
    { id: 2, name: "Nova Steam Next Fest", game_id: 1, game_name: "Project Nova", description: null, start_date: "2026-10-14", end_date: "2026-10-21", status: "planned", keywords: [], target_platforms: [], posts: 0, engagement: null, views: null },
    { id: 3, name: "Skyforge Kickstarter", game_id: 2, game_name: "Skyforge Tales", description: null, start_date: "2026-09-01", end_date: null, status: "active", keywords: [], target_platforms: ["Facebook"], posts: 1, engagement: 45, views: null },
  ];
  const inboxItems: (InboxItem & { audience: "user" | "admin"; user_id: number })[] = [
    { id: 1, audience: "admin", user_id: 2, kind: "flag", title: "Burak Yıldız yönetici incelemesi bekliyor", body: "🚨 KRİTİK AKTİVİTE UYARISI\nKullanıcı: Burak Yıldız\nGönderilen uyarılar: 3/3", created_at: ago(HOUR * 5), read_at: null, user_name: "Burak Yıldız" },
    { id: 2, audience: "user", user_id: 3, kind: "strike", title: "Paylaşım hatırlatması 1/3", body: "⚠️ Cem Kaya: 3 gündür yeni paylaşım linki eklemedin. Uyarı 1/3.", created_at: ago(HOUR * 20), read_at: null, user_name: "Cem Kaya" },
    { id: 3, audience: "user", user_id: 1, kind: "strike", title: "Haftalık özet", body: "Bu hafta 3 paylaşım, 372 etkileşim. Böyle devam!", created_at: ago(HOUR * 30), read_at: ago(HOUR * 29), user_name: "Ayşe Demir" },
  ];
  const engagementOf = (r: PostRow): number | null =>
    r.likes === null && r.comments === null && r.shares === null ? null : (r.likes ?? 0) + (r.comments ?? 0) + (r.shares ?? 0);
  const breakdown = (rows: PostRow[], key: (r: PostRow) => string | number | null, name?: (k: string | number) => string): BreakdownRow[] => {
    const groups = new Map<string | number, PostRow[]>();
    for (const r of rows) {
      const k = key(r);
      if (k === null) continue;
      groups.set(k, [...(groups.get(k) ?? []), r]);
    }
    return [...groups.entries()].map(([k, list]) => {
      const engs = list.map(engagementOf).filter((v): v is number => v !== null);
      return {
        key: k,
        name: name ? name(k) : String(k),
        posts: list.length,
        likes: sum(list, "likes"),
        comments: sum(list, "comments"),
        shares: sum(list, "shares"),
        views: sum(list, "views"),
        engagement: engs.length ? engs.reduce((a, b) => a + b, 0) : null,
        avg_engagement: engs.length ? Math.round((engs.reduce((a, b) => a + b, 0) / engs.length) * 10) / 10 : null,
        avg_sentiment: null,
        community_count: new Set(list.map((r) => r.community_name)).size,
        active_days: new Set(list.map((r) => r.posted_at.slice(0, 10))).size,
      };
    });
  };
  const analytics = (payload: Record<string, unknown>): AnalyticsOverview => {
    const userId = typeof payload.user_id === "number" ? payload.user_id : null;
    const rows = posts.filter((p) => (userId === null || p.user_id === userId)
      && (typeof payload.campaign_id !== "number" || p.campaign_id === payload.campaign_id)
      && (typeof payload.platform !== "string" || p.platform === payload.platform));
    const totals = breakdown(rows, () => "all")[0] ?? { key: "all", posts: 0, likes: null, comments: null, shares: null, views: null, engagement: null, avg_engagement: null, avg_sentiment: null, community_count: 0, active_days: 0 };
    const scores: Record<number, number> = { 1: 71.4, 3: 48.2, 2: 12.5, 4: 0 };
    const board: LeaderboardRow[] = people
      .filter((p) => userId === null || p.id === userId)
      .map((p) => {
        const own = breakdown(rows.filter((r) => r.user_id === p.id), () => "u")[0];
        return {
          ...(own ?? { key: "u", posts: 0, likes: null, comments: null, shares: null, views: null, engagement: null, avg_engagement: null, avg_sentiment: null, community_count: 0, active_days: 0 }),
          rank: 0, user_id: p.id, name: p.name, team_name: p.team_name, posts_per_week: own ? Math.round((own.posts / 4.3) * 100) / 100 : 0,
          warnings: p.total_strikes, current_warnings: p.strike_count, last_activity: p.last_post_at,
          components: { post_consistency: 0.8, engagement_score: 0.7, sentiment_score: 0.75, community_diversity: 0.5, engagement_velocity: 0.6, campaign_contribution: 1 },
          performance_score: scores[p.id] ?? 0,
        };
      })
      .sort((a, b) => b.performance_score - a.performance_score)
      .map((row, i) => ({ ...row, rank: i + 1 }));
    return {
      totals,
      weights: { post_consistency: 0.2, engagement_score: 0.3, sentiment_score: 0.15, community_diversity: 0.1, engagement_velocity: 0.15, campaign_contribution: 0.1 },
      leaderboard: board,
      platforms: breakdown(rows, (r) => r.platform),
      content_types: breakdown(rows, (r) => r.content_type),
      campaigns: breakdown(rows, (r) => r.campaign_id, (k) => campaigns.find((c) => c.id === k)?.name ?? "—"),
      games: breakdown(rows, (r) => r.game_id, (k) => games.find((g) => g.id === k)?.name ?? "—"),
      communities: breakdown(rows, (r) => r.community_name),
      topics: [
        { key: "release_question", label: "Çıkış / erişim sorusu", count: 9, positive: 2, negative: 0 },
        { key: "gameplay_praise", label: "Oynanış övgüsü", count: 7, positive: 7, negative: 0 },
        { key: "bug", label: "Hata / bug şikâyeti", count: 5, positive: 0, negative: 5 },
        { key: "price", label: "Fiyat", count: 3, positive: 0, negative: 1 },
      ],
      topic_labels: {},
    };
  };
  const reason = (tone: RecommendationItem["reasons"][number]["tone"], text: string) => ({ tone, text });
  const recommendationItems = (): RecommendationItem[] =>
    communities.filter((c) => c.status !== "blocked").map((c, i) => ({
      id: c.id, name: c.name, platform: c.platform, url: c.url, member_count: c.member_count, language: "en", status: c.status,
      favorite: c.favorite, last_used: c.last_used, previous_posts: c.previous_posts, days_since_last_post: c.last_used ? 4 : null,
      score: [61.5, 78.2, 66.0][i] ?? 50,
      components: { relevance: 0.6, activity: c.member_count ? 0.9 : null, engagement_history: c.previous_posts ? 0.8 : null, freshness: c.last_used ? 0.2 : 1, language_match: 1, audience_match: 0.5 },
      penalties: { spam: 2.5, recency: c.last_used ? 15 : 0, irrelevance: 0 },
      reasons: c.last_used
        ? [reason("plus", "FPS, Extraction Shooter oyuncu kitlesiyle yüksek eşleşme"), reason("plus", "Ekibin önceki paylaşımları burada iyi etkileşim aldı"), reason("minus", "Yakın zamanda kullanıldı (4 gün önce)")]
        : [reason("plus", "Project Nova ile güçlü konu uyumu (%67)"), reason("plus", "Daha önce hiç paylaşım yapılmamış"), reason("plus", "İngilizce hedef kitlenizle uyumlu"), ...(c.member_count ? [] : [reason("info", "Üye sayısı bilinmiyor")])],
    })).sort((a, b) => b.favorite - a.favorite || b.score - a.score);

  const sum = (rows: PostRow[], key: "likes" | "comments" | "shares" | "views"): number | null => {
    const known = rows.map((r) => r[key]).filter((v): v is number => v !== null);
    return known.length ? known.reduce((a, b) => a + b, 0) : null;
  };
  const avg = (rows: PostRow[], key: "positive" | "negative"): number | null => {
    const known = rows.map((r) => r[key]).filter((v): v is number => v !== null);
    return known.length ? Math.round((known.reduce((a, b) => a + b, 0) / known.length) * 100) / 100 : null;
  };

  const state = (payload: Record<string, unknown> = {}): EngineState => {
    const userId = typeof payload.user_id === "number" ? payload.user_id : null;
    const teamId = typeof payload.team_id === "number" ? payload.team_id : null;
    const ownPeople = people.filter((p) => (userId === null || p.id === userId) && (teamId === null || p.team_id === teamId));
    const ownIds = new Set(ownPeople.map((p) => p.id));
    const ownPosts = posts.filter((p) => ownIds.has(p.user_id));
    const ownNames = new Set(ownPeople.map((p) => p.name));
    return {
    generated_at: ago(0),
    team_filter: null,
    user_filter: userId,
    accounts: people.filter((p) => p.status !== "inactive").map((p) => ({ id: p.id, name: p.name, role: p.role, team_id: p.team_id, team_name: p.team_name })),
    games,
    campaigns,
    inbox_unread: inboxItems.filter((i) => !i.read_at && (userId === null ? i.audience === "admin" : i.audience === "user" && i.user_id === userId)).length,
    provider_mode: "real",
    kpis: {
      posts: ownPosts.length,
      posts_without_metrics: ownPosts.filter((p) => p.likes === null && p.views === null && p.comments === null && p.shares === null).length,
      users_total: ownPeople.length,
      users_active: ownPeople.filter((p) => p.status === "active").length,
      users_flagged: ownPeople.filter((p) => p.status === "flagged").length,
      likes: sum(ownPosts, "likes"),
      comments: sum(ownPosts, "comments"),
      shares: sum(ownPosts, "shares"),
      views: sum(ownPosts, "views"),
      avg_positive: avg(ownPosts, "positive"),
      avg_negative: avg(ownPosts, "negative"),
    },
    posts: [...ownPosts].reverse(),
    people: ownPeople,
    teams,
    communities,
    providers: [
      { platform: "X", consecutive_blocks: 0, paused_until: null, paused: false, last_success_at: ago(HOUR * 1.5), last_failure_at: null, last_error: null },
      { platform: "Instagram", consecutive_blocks: 0, paused_until: null, paused: false, last_success_at: null, last_failure_at: ago(HOUR * 2), last_error: "Instagram giriş istiyor" },
      { platform: "Threads", consecutive_blocks: 2, paused_until: ago(-HOUR * 5), paused: true, last_success_at: ago(HOUR * 8), last_failure_at: ago(HOUR), last_error: "Bot koruması/hız sınırı görüldü" },
    ],
    notifications: (
      [
      { id: 3, kind: "flag", status: "pending", attempts: 0, last_error: null, created_at: ago(HOUR * 5), sent_at: null, user_name: "Burak Yıldız" },
      { id: 2, kind: "strike", status: "suppressed", attempts: 0, last_error: "Bildirimler açılmadan önce oluştu", created_at: ago(HOUR * 29), sent_at: null, user_name: "Burak Yıldız" },
      { id: 1, kind: "strike", status: "no_target", attempts: 0, last_error: null, created_at: ago(HOUR * 20), sent_at: null, user_name: "Cem Kaya" },
      ] as NotificationRow[]
    ).filter((n) => userId === null || (n.user_name !== null && ownNames.has(n.user_name))),
    notification_summary: userId === null ? { pending: 1, suppressed: 1, no_target: 1 } : {},
    settings: { values: { ...values }, spec: SPEC },
    security: { pin_set: pinSet, telegram_token_set: false, secrets: { ...secretState } },
  };
  };

  const requireAdmin = (given: string | null) => {
    if (!given) throw new Failure("PERMISSION_DENIED", "Bu işlem için yönetici PIN'i gerekir");
    if (given !== pin) throw new Failure("PERMISSION_DENIED", "Yönetici PIN'i hatalı");
  };

  const context = (name: string): PostingContext => {
    const key = name.toLowerCase().replace(/^\/?r\//, "");
    const found = communities.find((c) => c.name.toLowerCase().replace(/^r\//, "") === key);
    if (!found || found.previous_posts === 0) {
      return { known: found !== undefined, community: null, previous_posts: 0, last_post: null, days_since_last_post: null, recent_posts: [], recommendation: "CLEAN", message: "Bu toplulukta henüz paylaşım yapılmadı (Temiz)" };
    }
    const noted = posts.find((x) => x.community_name === found.name && x.note);
    const entry = { posted_at: found.last_used ?? ago(0), user: "Mehmet Aksoy", team: "Marketing B", preview: "After three years of development, our extraction shooter is finally playable", url: "https://x.com/m/status/1", note: noted?.note ?? null };
    return { known: true, community: { id: found.id, name: found.name, platform: found.platform, status: found.status }, previous_posts: found.previous_posts, last_post: entry, days_since_last_post: 4, recent_posts: [entry], recommendation: "RECENTLY_USED", message: "Yakın zamanda kullanılmış bir topluluk." };
  };

  const handlers: Record<string, (p: Record<string, unknown>, given: string | null) => unknown> = {
    health: () => ({ api_version: "v1", provider_mode: "real", version: "0.1.0-preview", author: "axthrowa", pin_set: pinSet, telegram_token_set: false, playwright_installed: false }),
    state,
    post_detail: (p) => {
      const found = posts.find((x) => x.id === p.post_id);
      if (!found) throw new Failure("NOT_FOUND", "Gönderi bulunamadı");
      return { post: found, snapshots, comments: comments.map((c, i) => ({ ...c, topics: [["release_question"], [], ["bug", "performance"], ["release_question"]][i] ?? [] })), analytics: { velocity_1h: 12, velocity_6h: 8.5, velocity_24h: 5.2, likes_growth: 130, views_growth: 5600, engagement_rate: 0.027 }, topic_labels: { release_question: "Çıkış / erişim sorusu", bug: "Hata / bug şikâyeti", performance: "Performans / optimizasyon" } };
    },
    posting_context: (p) => context(String(p.name ?? "")),
    add_post: (p) => {
      const user = people.find((x) => x.id === p.user_id);
      if (!user) throw new Failure("NOT_FOUND", "Kullanıcı bulunamadı");
      const url = String(p.url ?? "");
      if (/localhost|127\.0\.0\.1|192\.168\./.test(url)) throw new Failure("UNSAFE_URL", "Yerel ağ adresleri kabul edilmez");
      const platform = /x\.com|twitter\.com/.test(url) ? "X" : /instagram/.test(url) ? "Instagram" : /facebook/.test(url) ? "Facebook" : /threads/.test(url) ? "Threads" : /reddit/.test(url) ? "Reddit" : /youtu/.test(url) ? "YouTube" : "Other";
      const id = nextId++;
      if (user.role === "viewer") throw new Failure("PERMISSION_DENIED", "İzleyici (viewer) rolündeki hesaplar paylaşım ekleyemez");
      const campaign = campaigns.find((c) => c.id === p.campaign_id) ?? null;
      const game = games.find((g) => g.id === (p.game_id ?? campaign?.game_id)) ?? null;
      posts.push(post({ id, platform, url, user_id: user.id, user_name: user.name, team_name: user.team_name, community_name: String(p.community_name ?? "") || null, note: String(p.note ?? "").trim() || null, posted_at: ago(0), content_type: (p.content_type as PostRow["content_type"]) ?? "post", campaign_id: campaign?.id ?? null, campaign_name: campaign?.name ?? null, game_id: game?.id ?? null, game_name: game?.name ?? null, last_source: null }));
      return { post_id: id, created: true, platform };
    },
    manual_metrics: () => ({}),
    update_note: (p) => {
      const found = posts.find((x) => x.id === p.post_id);
      if (!found) throw new Failure("NOT_FOUND", "Gönderi bulunamadı");
      const note = String(p.note ?? "").trim();
      if (note.length > 500) throw new Failure("VALIDATION", "Not en çok 500 karakter olabilir");
      found.note = note || null;
      return { note: found.note };
    },
    manual_comments: (p) => ({ added: Array.isArray(p.texts) ? p.texts.length : 0 }),
    refresh: () => ({ checked: 1, ok: 0, unavailable: 1, auth_required: 0, skipped_paused: 0, errors: ["Önizleme modunda ölçüm yapılmaz"] }),
    add_community: (p) => ({ community_id: communities.push({ id: nextId++, name: String(p.name), platform: "Other", url: null, category: null, member_count: null, status: "approved", favorite: 0, relevance_score: null, activity_score: null, reason: "Elle eklendi", discovered_at: ago(0), last_used: null, previous_posts: 0 }) }),
    community_state: (p, given) => {
      if (p.status) requireAdmin(given);
      return {};
    },
    settings_get: (p) => ({ values: { ...values, ...(teamOverrides.get(Number(p.team_id)) ?? {}) }, spec: SPEC, overrides: teamOverrides.get(Number(p.team_id)) ?? {} }),
    verify_pin: (_p, given) => requireAdmin(given),
    set_pin: (p) => {
      if (pinSet && p.current_pin !== pin) throw new Failure("PERMISSION_DENIED", "Yönetici PIN'i hatalı");
      pin = String(p.new_pin);
      pinSet = true;
      return {};
    },
    add_team: (p, given) => {
      requireAdmin(given);
      const id = nextId++;
      teams.push({ id, name: String(p.name), chat_id: null, members: 0, flagged: 0 });
      return { team_id: id };
    },
    update_team: (_p, given) => requireAdmin(given),
    add_user: (p, given) => {
      requireAdmin(given);
      const id = nextId++;
      const team = teams.find((t) => t.id === p.team_id);
      people.push(person({ id, name: String(p.name), team_id: team?.id ?? null, team_name: team?.name ?? null, last_post_at: null, days_since_last_post: null }));
      return { user_id: id };
    },
    update_user: (_p, given) => requireAdmin(given),
    settings_set: (p, given) => {
      requireAdmin(given);
      const changes = (p.changes ?? {}) as Record<string, SettingValue>;
      for (const [key, value] of Object.entries(changes)) {
        const spec = SPEC.find((s) => s.key === key);
        if (!spec) throw new Failure("VALIDATION", `Bilinmeyen ayar: ${key}`);
        if (spec.kind === "int" && (typeof value !== "number" || value < spec.low || value > spec.high)) throw new Failure("VALIDATION", `${key}: ${spec.low}-${spec.high} aralığında olmalı`);
      }
      if (typeof p.team_id === "number") teamOverrides.set(p.team_id, { ...(teamOverrides.get(p.team_id) ?? {}), ...changes });
      else Object.assign(values, changes);
      return {};
    },
    settings_clear_override: (p, given) => {
      requireAdmin(given);
      const current = teamOverrides.get(Number(p.team_id));
      if (current) delete current[String(p.key)];
      return {};
    },
    discover: (_p, given) => {
      requireAdmin(given);
      return { found: 0, added: 0, queries: 0, unavailable: ["Önizleme modunda keşif yapılmaz"] };
    },
    strike_check: (_p, given) => {
      requireAdmin(given);
      return { strikes: [{ user: "Cem Kaya", number: 2, flagged: false }] };
    },
    flush: (_p, given) => {
      requireAdmin(given);
      return { sent: 0, failed: 0, retrying: 0, suppressed: 0, held: true };
    },
    set_telegram_token: (_p, given) => requireAdmin(given),
    clear_telegram_token: (_p, given) => requireAdmin(given),
    test_telegram: (_p, given) => requireAdmin(given),
    login_session: (_p, given) => requireAdmin(given),
    analytics: (p) => analytics(p),
    community_recommendations: (p) => ({ target: typeof p.game_id === "number" ? games.find((g) => g.id === p.game_id)?.name ?? null : null, keywords: ["FPS oyunları"], items: recommendationItems() }),
    add_game: (p, given) => {
      requireAdmin(given);
      const name = String(p.name ?? "").trim();
      if (!name) throw new Failure("VALIDATION", "Oyun adı 1-120 karakter olmalı");
      const id = nextId++;
      games.push({ id, name, genres: (p.genres as string[]) ?? [], keywords: (p.keywords as string[]) ?? [], languages: (p.languages as string[]) ?? [], website: null, steam_url: null, status: "active", posts: 0 });
      return { game_id: id };
    },
    update_game: (p, given) => {
      requireAdmin(given);
      const g = games.find((x) => x.id === p.game_id);
      if (g) Object.assign(g, p.fields as object);
      return {};
    },
    add_campaign: (p, given) => {
      requireAdmin(given);
      const name = String(p.name ?? "").trim();
      if (!name) throw new Failure("VALIDATION", "Kampanya adı 1-120 karakter olmalı");
      const game = games.find((g) => g.id === p.game_id) ?? null;
      const id = nextId++;
      campaigns.push({ id, name, game_id: game?.id ?? null, game_name: game?.name ?? null, description: (p.description as string) ?? null, start_date: (p.start_date as string) || null, end_date: (p.end_date as string) || null, status: (p.status as Campaign["status"]) ?? "active", keywords: [], target_platforms: [], posts: 0, engagement: null, views: null });
      return { campaign_id: id };
    },
    update_campaign: (p, given) => {
      requireAdmin(given);
      const c = campaigns.find((x) => x.id === p.campaign_id);
      if (c) Object.assign(c, p.fields as object);
      return {};
    },
    archive_post: (p, given) => {
      requireAdmin(given);
      const index = posts.findIndex((x) => x.id === p.post_id);
      if (index >= 0 && p.archived !== false) posts.splice(index, 1);
      return { archived: p.archived !== false };
    },
    inbox: (p, given) => {
      if (p.admin === true) requireAdmin(given);
      const items = inboxItems.filter((i) => (p.admin === true ? i.audience === "admin" : i.audience === "user" && i.user_id === p.user_id));
      return { items, unread: items.filter((i) => !i.read_at).length };
    },
    inbox_read: (p, given) => {
      if (p.admin === true) requireAdmin(given);
      let marked = 0;
      for (const item of inboxItems) {
        const mine = p.admin === true ? item.audience === "admin" : item.audience === "user" && item.user_id === p.user_id;
        const wanted = !Array.isArray(p.ids) || (p.ids as number[]).includes(item.id);
        if (mine && wanted && !item.read_at) {
          item.read_at = ago(0);
          marked += 1;
        }
      }
      return { marked };
    },
    set_secret: (p, given) => {
      requireAdmin(given);
      secretState[String(p.name)] = true;
      return { ...secretState };
    },
    clear_secret: (p, given) => {
      requireAdmin(given);
      secretState[String(p.name)] = false;
      return { ...secretState };
    },
    test_email: (_p, given) => {
      requireAdmin(given);
      throw new Failure("ENGINE_ERROR", "Önizleme modunda e-posta gönderilmez");
    },
    test_teams: (_p, given) => {
      requireAdmin(given);
      throw new Failure("ENGINE_ERROR", "Önizleme modunda Teams mesajı gönderilmez");
    },
    system_overview: (_p, given) => {
      requireAdmin(given);
      return {
        jobs: {
          items: [
            { id: 4, name: "refresh", started_at: ago(HOUR), finished_at: ago(HOUR * 0.98), status: "ok", detail: "{'checked': 5, 'ok': 3}", trigger: "schedule" },
            { id: 3, name: "strike_check", started_at: ago(HOUR * 12), finished_at: ago(HOUR * 12), status: "ok", detail: "1 uyarı", trigger: "schedule" },
            { id: 2, name: "discovery", started_at: ago(HOUR * 20), finished_at: ago(HOUR * 20), status: "error", detail: "ProviderUnavailable: Reddit araması kullanılamıyor (HTTP 429)", trigger: "schedule" },
            { id: 1, name: "backup", started_at: ago(HOUR * 22), finished_at: ago(HOUR * 22), status: "ok", detail: "etkilesim-20261008.db", trigger: "schedule" },
          ],
          summary: { ok: 3, error: 1 },
          latest: {
            refresh: { label: "Etkileşim ölçümü", status: "ok", started_at: ago(HOUR) },
            strike_check: { label: "Hareketsizlik kontrolü", status: "ok", started_at: ago(HOUR * 12) },
            discovery: { label: "Topluluk keşfi", status: "error", started_at: ago(HOUR * 20) },
            flush: { label: "Bildirim gönderimi", status: null },
            retention: { label: "Saklama süresi temizliği", status: null },
            backup: { label: "Veritabanı yedeği", status: "ok", started_at: ago(HOUR * 22) },
          },
        },
        providers: [
          { platform: "X", circuit: "CLOSED", paused_until: null, consecutive_blocks: 0, success_rate: 0.92, attempts_7d: 25, queue: 1, last_success_at: ago(HOUR * 1.5), last_failure_at: null, last_error: null },
          { platform: "Instagram", circuit: "CLOSED", paused_until: null, consecutive_blocks: 0, success_rate: 0, attempts_7d: 6, queue: 0, last_success_at: null, last_failure_at: ago(HOUR * 2), last_error: "Instagram giriş istiyor" },
          { platform: "Threads", circuit: "OPEN", paused_until: ago(-HOUR * 5), consecutive_blocks: 2, success_rate: 0.4, attempts_7d: 5, queue: 2, last_success_at: ago(HOUR * 8), last_failure_at: ago(HOUR), last_error: "Bot koruması/hız sınırı görüldü" },
          { platform: "Reddit", circuit: "HALF_OPEN", paused_until: null, consecutive_blocks: 1, success_rate: 0.8, attempts_7d: 10, queue: 0, last_success_at: ago(HOUR * 3), last_failure_at: ago(HOUR * 4), last_error: "HTTP 429" },
        ],
        audit: [
          { id: 3, actor: "admin", action: "settings.set", entity: "setting", entity_id: "global:inactivity_days", detail: { old: 3, new: 3 }, at: ago(HOUR * 3) },
          { id: 2, actor: "system", action: "strike.issued", entity: "user", entity_id: "2", detail: { number: 3, flagged: true }, at: ago(HOUR * 5) },
          { id: 1, actor: "Ayşe Demir", action: "post.create", entity: "post", entity_id: "1", detail: { platform: "X" }, at: ago(HOUR * 30) },
        ],
        warnings: [
          { id: 3, strike_number: 3, reason: "6 gün paylaşım yok", triggered_at: ago(HOUR * 5), resolved_at: null, user_name: "Burak Yıldız", team_name: "Marketing A" },
          { id: 2, strike_number: 1, reason: "3 gün paylaşım yok", triggered_at: ago(HOUR * 20), resolved_at: null, user_name: "Cem Kaya", team_name: "Marketing B" },
        ],
      };
    },
    run_job: (_p, given) => {
      requireAdmin(given);
      throw new Failure("ENGINE_ERROR", "Önizleme modunda işler çalıştırılmaz");
    },
    retry_failed: (_p, given) => {
      requireAdmin(given);
      return { notifications: 0, posts: 1 };
    },
    retention: (_p, given) => {
      requireAdmin(given);
      return {};
    },
    backup: (_p, given) => {
      requireAdmin(given);
      throw new Failure("ENGINE_ERROR", "Önizleme modunda yedek alınmaz");
    },
    export: (_p, given) => {
      requireAdmin(given);
      throw new Failure("ENGINE_ERROR", "Önizleme modunda dosya oluşturulmaz");
    },
    search: (p) => {
      const q = String(p.query ?? "").toLocaleLowerCase("tr-TR").trim();
      if (q.length < 2) throw new Failure("VALIDATION", "Arama için en az 2 karakter yazın");
      const userId = typeof p.user_id === "number" ? p.user_id : null;
      const has = (v: string | null) => (v ?? "").toLocaleLowerCase("tr-TR").includes(q);
      return {
        posts: posts.filter((x) => (userId === null || x.user_id === userId) && (has(x.url) || has(x.note) || has(x.community_name) || has(x.user_name))).slice(0, 8).map((x) => ({ id: x.id, platform: x.platform, url: x.url, user_name: x.user_name, community_name: x.community_name, note: x.note })),
        people: userId === null ? people.filter((x) => has(x.name)).map((x) => ({ id: x.id, name: x.name, team_name: x.team_name })) : [],
        communities: communities.filter((x) => has(x.name)).map((x) => ({ id: x.id, name: x.name, platform: x.platform })),
        campaigns: campaigns.filter((x) => has(x.name)).map((x) => ({ id: x.id, name: x.name, status: x.status })),
        games: games.filter((x) => has(x.name)).map((x) => ({ id: x.id, name: x.name, status: x.status })),
      };
    },
    seed_demo: (_p, given) => {
      requireAdmin(given);
      throw new Failure("VALIDATION", "Tohum verisi yalnızca boş veritabanına eklenebilir");
    },
    metrics: () => ({ content_type: "text/plain", text: "" }),
  };

  return {
    invoke: async (command, args) => {
      await new Promise((resolve) => window.setTimeout(resolve, 60));
      const handler = handlers[command];
      if (!handler) throw new Failure("NOT_FOUND", `Bilinmeyen komut: ${command}`);
      try {
        const result = handler(args.payload, args.pin);
        return result === undefined ? {} : result;
      } catch (error) {
        if (error instanceof Failure) throw { code: error.code, message: error.message };
        throw error;
      }
    },
  };
}
