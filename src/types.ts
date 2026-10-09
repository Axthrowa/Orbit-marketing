// Motor (engine/etkilesim/dashboard.py) yanıtlarının tip karşılıkları.
// Bilinmeyen sayaçlar `null`dır; arayüz bunları "—" olarak gösterir, asla 0 olarak değil.

export type Platform =
  | "X"
  | "Instagram"
  | "Facebook"
  | "Threads"
  | "Reddit"
  | "YouTube"
  | "Forum"
  | "Other";

export type DataStatus =
  | "PENDING"
  | "OK"
  | "DATA_UNAVAILABLE"
  | "AUTHORIZATION_REQUIRED"
  | "MANUAL";

export type UserStatus = "active" | "flagged" | "inactive";
export type Role = "admin" | "manager" | "member" | "viewer";
export type Recommendation = "CLEAN" | "AVOID" | "RECENTLY_USED" | "CAUTION" | "SAFE";
export type CommentLabel = "POSITIVE" | "NEUTRAL" | "NEGATIVE" | "MIXED" | "UNKNOWN";
export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

export interface Kpis {
  posts: number;
  posts_without_metrics: number;
  users_total: number;
  users_active: number;
  users_flagged: number;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  views: number | null;
  avg_positive: number | null;
  avg_negative: number | null;
}

export interface PostRow {
  id: number;
  platform: Platform;
  url: string;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  views: number | null;
  initial_likes: number | null;
  positive: number | null;
  negative: number | null;
  sentiment_sample: number;
  data_status: DataStatus;
  last_error: string | null;
  last_metrics_at: string | null;
  last_attempt_at: string | null;
  posted_at: string;
  preview_text: string | null;
  note: string | null;
  content_type: ContentType;
  game_id: number | null;
  campaign_id: number | null;
  game_name: string | null;
  campaign_name: string | null;
  last_source: "SCRAPE" | "HTTP" | "MANUAL" | "MOCK" | null;
  user_id: number;
  user_name: string;
  team_name: string | null;
  community_name: string | null;
}

export interface PersonRow {
  id: number;
  name: string;
  role: Role;
  team_id: number | null;
  team_name: string | null;
  has_telegram: boolean;
  has_email?: boolean;
  strike_count: number;
  total_strikes: number;
  max_strikes: number;
  inactivity_days: number;
  status: UserStatus;
  last_post_at: string | null;
  flagged_at: string | null;
  posts: number;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  views: number | null;
  engagement: number | null;
  days_since_last_post: number | null;
}

export interface TeamRow {
  id: number;
  name: string;
  chat_id: string | null;
  members: number;
  flagged: number;
}

export interface CommunityRow {
  id: number;
  name: string;
  platform: string;
  url: string | null;
  category: string | null;
  member_count: number | null;
  status: "discovered" | "approved" | "blocked";
  favorite: number;
  relevance_score: number | null;
  activity_score: number | null;
  reason: string | null;
  discovered_at: string;
  last_used: string | null;
  previous_posts: number;
}

export interface ProviderRow {
  platform: string;
  consecutive_blocks: number;
  paused_until: string | null;
  paused: boolean;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string | null;
}

export interface NotificationRow {
  channel?: "TELEGRAM" | "EMAIL" | "TEAMS";
  id: number;
  kind: string;
  status: "pending" | "sent" | "failed" | "suppressed" | "no_target";
  attempts: number;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
  user_name: string | null;
}

export type SettingKind = "int" | "bool" | "time" | "str" | "list" | "enum";

export interface SettingSpec {
  key: string;
  kind: SettingKind;
  label: string;
  default: unknown;
  low: number;
  high: number;
  choices: string[];
  team_overridable: boolean;
}

export type SettingValue = number | boolean | string | string[];

export interface Account {
  id: number;
  name: string;
  role: Role;
  team_id: number | null;
  team_name: string | null;
}

export interface EngineState {
  generated_at: string;
  team_filter: number | null;
  user_filter: number | null;
  accounts: Account[];
  games: Game[];
  campaigns: Campaign[];
  inbox_unread: number;
  provider_mode: "real" | "mock";
  kpis: Kpis;
  posts: PostRow[];
  people: PersonRow[];
  teams: TeamRow[];
  communities: CommunityRow[];
  providers: ProviderRow[];
  notifications: NotificationRow[];
  notification_summary: Record<string, number>;
  settings: { values: Record<string, SettingValue>; spec: SettingSpec[] };
  security: { pin_set: boolean; telegram_token_set: boolean; secrets?: Record<string, boolean> };
}

export interface SettingsView {
  values: Record<string, SettingValue>;
  spec: SettingSpec[];
  overrides: Record<string, SettingValue>;
}

export interface HistoryEntry {
  posted_at: string;
  user: string;
  team: string | null;
  preview: string;
  url: string;
  note: string | null;
  campaign?: string | null;
}

export interface PostingContext {
  known: boolean;
  community: { id: number; name: string; platform: string; status: string } | null;
  previous_posts: number;
  last_post: HistoryEntry | null;
  days_since_last_post: number | null;
  recent_posts: HistoryEntry[];
  recommendation: Recommendation;
  message: string;
}

export interface Snapshot {
  likes: number | null;
  comments: number | null;
  shares: number | null;
  views: number | null;
  source: "SCRAPE" | "HTTP" | "MANUAL" | "MOCK";
  captured_at: string;
}

export interface CommentRow {
  topics?: string[];
  text: string;
  language: string | null;
  label: CommentLabel;
  positive: number;
  negative: number;
}

export interface PostDetail {
  post: PostRow;
  analytics?: Record<string, number | null>;
  topic_labels?: Record<string, string>;
  snapshots: Snapshot[];
  comments: CommentRow[];
}

export interface RefreshSummary {
  checked: number;
  ok: number;
  unavailable: number;
  auth_required: number;
  skipped_paused: number;
  errors: string[];
}

export interface AddPostInput {
  user_id: number;
  url: string;
  community_name?: string;
  preview_text?: string;
  note?: string;
  posted_at?: string;
  game_id?: number;
  campaign_id?: number;
  content_type?: ContentType;
}

export interface AddPostResult {
  post_id: number;
  created: boolean;
  platform: Platform;
}

export interface Health {
  version: string;
  author: string;
  pin_set: boolean;
  telegram_token_set: boolean;
  playwright_installed: boolean;
}

// ---------------------------------------------------------------- master prompt tamamlama (P2–P9)

export type ContentType = "post" | "video" | "image" | "poll" | "event" | "other";
export type CampaignStatus = "planned" | "active" | "finished" | "archived";

export interface Game {
  id: number;
  name: string;
  genres: string[];
  keywords: string[];
  languages: string[];
  website: string | null;
  steam_url: string | null;
  status: "active" | "archived";
  posts: number;
}

export interface Campaign {
  id: number;
  name: string;
  game_id: number | null;
  game_name: string | null;
  description: string | null;
  start_date: string | null;
  end_date: string | null;
  status: CampaignStatus;
  keywords: string[];
  target_platforms: string[];
  posts: number;
  engagement: number | null;
  views: number | null;
}

export interface BreakdownRow {
  key: string | number;
  name?: string;
  posts: number;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  views: number | null;
  engagement: number | null;
  avg_engagement: number | null;
  avg_sentiment: number | null;
  community_count: number;
  active_days: number;
}

export interface LeaderboardRow extends BreakdownRow {
  rank: number;
  user_id: number;
  name: string;
  team_name: string | null;
  posts_per_week: number | null;
  warnings: number;
  current_warnings: number;
  last_activity: string | null;
  components: Record<string, number>;
  performance_score: number;
}

export interface TopicCount {
  key: string;
  label: string;
  count: number;
  positive: number;
  negative: number;
}

export interface AnalyticsOverview {
  totals: BreakdownRow;
  weights: Record<string, number>;
  leaderboard: LeaderboardRow[];
  platforms: BreakdownRow[];
  content_types: BreakdownRow[];
  campaigns: BreakdownRow[];
  games: BreakdownRow[];
  communities: BreakdownRow[];
  topics: TopicCount[];
  topic_labels: Record<string, string>;
}

export interface AnalyticsFilters {
  days: number | null;
  campaign_id?: number | null;
  game_id?: number | null;
  platform?: string | null;
  team_id?: number | null;
  user_id?: number | null;
}

export interface RecommendationReason {
  tone: "plus" | "minus" | "info";
  text: string;
}

export interface RecommendationItem {
  id: number;
  name: string;
  platform: string;
  url: string | null;
  member_count: number | null;
  language: string | null;
  status: string;
  favorite: number;
  last_used: string | null;
  previous_posts: number;
  days_since_last_post: number | null;
  score: number;
  components: Record<string, number | null>;
  penalties: Record<string, number>;
  reasons: RecommendationReason[];
}

export interface Recommendations {
  target: string | null;
  keywords: string[];
  items: RecommendationItem[];
}

export interface InboxItem {
  id: number;
  kind: string;
  title: string;
  body: string;
  created_at: string;
  read_at: string | null;
  user_name: string | null;
}

export interface JobRun {
  id: number;
  name: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "ok" | "error";
  detail: string | null;
  trigger: "schedule" | "manual";
}

export interface ProviderHealth {
  platform: string;
  circuit: "CLOSED" | "OPEN" | "HALF_OPEN";
  paused_until: string | null;
  consecutive_blocks: number;
  success_rate: number | null;
  attempts_7d: number;
  queue: number;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string | null;
}

export interface AuditEntry {
  id: number;
  actor: string;
  action: string;
  entity: string | null;
  entity_id: string | null;
  detail: unknown;
  at: string;
}

export interface WarningEvent {
  id: number;
  strike_number: number;
  reason: string;
  triggered_at: string;
  resolved_at: string | null;
  user_name: string;
  team_name: string | null;
}

export interface SystemOverview {
  jobs: {
    items: JobRun[];
    summary: Record<string, number>;
    latest: Record<string, { label: string; status: string | null; started_at?: string; detail?: string | null }>;
  };
  providers: ProviderHealth[];
  audit: AuditEntry[];
  warnings: WarningEvent[];
}

export interface SearchResults {
  posts: { id: number; platform: string; url: string; user_name: string; community_name: string | null; note: string | null }[];
  people: { id: number; name: string; team_name: string | null }[];
  communities: { id: number; name: string; platform: string }[];
  campaigns: { id: number; name: string; status: string }[];
  games: { id: number; name: string; status: string }[];
}
