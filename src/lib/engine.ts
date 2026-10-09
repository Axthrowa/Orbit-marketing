import type {
  AnalyticsFilters,
  AnalyticsOverview,
  InboxItem,
  Recommendations,
  SearchResults,
  SystemOverview,
  AddPostInput,
  AddPostResult,
  EngineState,
  Health,
  PostDetail,
  PostingContext,
  RefreshSummary,
  SettingValue,
  SettingsView,
} from "../types";

/** Motorun hata sözleşmesi: {code, message}. */
export class EngineError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "EngineError";
    this.code = code;
  }
}

export interface EngineTransport {
  /** Tauri komutunu (veya önizleme taklidini) çağırır. Hata durumunda reddeder. */
  invoke(command: string, args: { payload: Record<string, unknown>; pin: string | null }): Promise<unknown>;
}

interface Failure {
  code: string;
  message: string;
}

function isFailure(value: unknown): value is Failure {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Failure).code === "string" &&
    typeof (value as Failure).message === "string"
  );
}

function toEngineError(error: unknown): EngineError {
  if (error instanceof EngineError) return error;
  if (isFailure(error)) return new EngineError(error.code, error.message);
  if (typeof error === "string") return new EngineError("INTERNAL", error);
  if (error instanceof Error) return new EngineError("INTERNAL", error.message);
  return new EngineError("INTERNAL", "Bilinmeyen hata");
}

export interface Engine {
  readonly isPreview: boolean;
  health(): Promise<Health>;
  state(teamId: number | null, userId?: number | null): Promise<EngineState>;
  postDetail(postId: number): Promise<PostDetail>;
  postingContext(input: { name?: string; url?: string; teamId?: number | null }): Promise<PostingContext>;
  addPost(input: AddPostInput): Promise<AddPostResult>;
  manualMetrics(input: {
    postId: number;
    likes?: string;
    comments?: string;
    shares?: string;
    views?: string;
  }): Promise<void>;
  manualComments(postId: number, texts: string[]): Promise<number>;
  updateNote(postId: number, note: string): Promise<string | null>;
  refresh(postIds?: number[]): Promise<RefreshSummary>;
  addCommunity(name: string, platform: string, url?: string): Promise<number>;
  communityState(
    communityId: number,
    change: { status?: "discovered" | "approved" | "blocked"; favorite?: boolean },
    pin: string | null,
  ): Promise<void>;
  settingsGet(teamId: number | null): Promise<SettingsView>;
  // Yönetici işlemleri (PIN gerekir)
  verifyPin(pin: string): Promise<void>;
  setPin(newPin: string, currentPin: string | null): Promise<void>;
  addTeam(pin: string, name: string, chatId: string): Promise<number>;
  updateTeam(pin: string, teamId: number, fields: Record<string, unknown>): Promise<void>;
  addUser(
    pin: string,
    input: { name: string; teamId: number | null; role: string; telegramId: string; email?: string },
  ): Promise<number>;
  updateUser(pin: string, userId: number, fields: Record<string, unknown>): Promise<void>;
  settingsSet(
    pin: string,
    changes: Record<string, SettingValue>,
    teamId: number | null,
  ): Promise<void>;
  settingsClearOverride(pin: string, key: string, teamId: number): Promise<void>;
  discover(pin: string): Promise<{ found: number; added: number; unavailable: string[] }>;
  strikeCheck(pin: string, nowIso?: string): Promise<{ strikes: { user: string; number: number; flagged: boolean }[] }>;
  flush(pin: string): Promise<{ sent: number; failed: number; retrying: number; suppressed: number; held: boolean }>;
  setTelegramToken(pin: string, token: string): Promise<void>;
  clearTelegramToken(pin: string): Promise<void>;
  testTelegram(pin: string, chatId: string): Promise<void>;
  loginSession(pin: string, platform: string): Promise<void>;
  analytics(filters: AnalyticsFilters): Promise<AnalyticsOverview>;
  recommendations(input: { gameId?: number | null; campaignId?: number | null; teamId?: number | null }): Promise<Recommendations>;
  addGame(pin: string, data: Record<string, unknown>): Promise<number>;
  updateGame(pin: string, gameId: number, fields: Record<string, unknown>): Promise<void>;
  addCampaign(pin: string, data: Record<string, unknown>): Promise<number>;
  updateCampaign(pin: string, campaignId: number, fields: Record<string, unknown>): Promise<void>;
  archivePost(pin: string, postId: number, archived: boolean): Promise<void>;
  inbox(viewer: { userId: number } | { admin: true }, pin: string | null): Promise<{ items: InboxItem[]; unread: number }>;
  inboxRead(viewer: { userId: number } | { admin: true }, ids: number[] | null, pin: string | null): Promise<number>;
  setSecret(pin: string, name: string, value: string): Promise<Record<string, boolean>>;
  clearSecret(pin: string, name: string): Promise<Record<string, boolean>>;
  testEmail(pin: string, to: string): Promise<void>;
  testTeams(pin: string): Promise<void>;
  systemOverview(pin: string, action?: string): Promise<SystemOverview>;
  runJob(pin: string, name: string): Promise<Record<string, unknown>>;
  retryFailed(pin: string): Promise<{ notifications: number; posts: number }>;
  backup(pin: string): Promise<{ path: string; removed: number }>;
  exportData(pin: string, format: "csv" | "xlsx" | "json"): Promise<{ path: string; rows: Record<string, number> }>;
  search(query: string, userId: number | null): Promise<SearchResults>;
  seedDemo(pin: string): Promise<Record<string, number>>;
  retention(pin: string): Promise<Record<string, number>>;
  metricsText(): Promise<string>;
}

export function createEngine(transport: EngineTransport, isPreview: boolean): Engine {
  const call = async <T>(
    command: string,
    payload: Record<string, unknown> = {},
    pin: string | null = null,
  ): Promise<T> => {
    try {
      return (await transport.invoke(command, { payload, pin })) as T;
    } catch (error) {
      throw toEngineError(error);
    }
  };

  return {
    isPreview,
    health: () => call<Health>("health"),
    state: (teamId, userId) => call<EngineState>("state", { team_id: teamId, user_id: userId ?? null }),
    postDetail: (postId) => call<PostDetail>("post_detail", { post_id: postId }),
    postingContext: ({ name, url, teamId }) =>
      call<PostingContext>("posting_context", { name, url, team_id: teamId ?? null }),
    addPost: (input) => call<AddPostResult>("add_post", { ...input }),
    manualMetrics: async ({ postId, likes, comments, shares, views }) => {
      await call("manual_metrics", { post_id: postId, likes, comments, shares, views });
    },
    manualComments: async (postId, texts) =>
      (await call<{ added: number }>("manual_comments", { post_id: postId, texts })).added,
    updateNote: async (postId, note) =>
      (await call<{ note: string | null }>("update_note", { post_id: postId, note })).note,
    refresh: (postIds) => call<RefreshSummary>("refresh", { post_ids: postIds ?? null }),
    addCommunity: async (name, platform, url) =>
      (await call<{ community_id: number }>("add_community", { name, platform, url })).community_id,
    communityState: async (communityId, change, pin) => {
      await call("community_state", { community_id: communityId, ...change }, pin);
    },
    settingsGet: (teamId) => call<SettingsView>("settings_get", { team_id: teamId }),
    verifyPin: async (pin) => {
      await call("verify_pin", {}, pin);
    },
    setPin: async (newPin, currentPin) => {
      await call("set_pin", { new_pin: newPin, current_pin: currentPin });
    },
    addTeam: async (pin, name, chatId) =>
      (await call<{ team_id: number }>("add_team", { name, chat_id: chatId }, pin)).team_id,
    updateTeam: async (pin, teamId, fields) => {
      await call("update_team", { team_id: teamId, fields }, pin);
    },
    addUser: async (pin, { name, teamId, role, telegramId, email }) =>
      (
        await call<{ user_id: number }>(
          "add_user",
          { name, team_id: teamId, role, telegram_id: telegramId, email: email || null },
          pin,
        )
      ).user_id,
    updateUser: async (pin, userId, fields) => {
      await call("update_user", { user_id: userId, fields }, pin);
    },
    settingsSet: async (pin, changes, teamId) => {
      await call("settings_set", { changes, team_id: teamId }, pin);
    },
    settingsClearOverride: async (pin, key, teamId) => {
      await call("settings_clear_override", { key, team_id: teamId }, pin);
    },
    discover: (pin) => call("discover", {}, pin),
    strikeCheck: (pin, nowIso) => call("strike_check", nowIso ? { now: nowIso } : {}, pin),
    flush: (pin) => call("flush", {}, pin),
    setTelegramToken: async (pin, token) => {
      await call("set_telegram_token", { token }, pin);
    },
    clearTelegramToken: async (pin) => {
      await call("clear_telegram_token", {}, pin);
    },
    testTelegram: async (pin, chatId) => {
      await call("test_telegram", { chat_id: chatId }, pin);
    },
    loginSession: async (pin, platform) => {
      await call("login_session", { platform }, pin);
    },
    analytics: (filters) => call<AnalyticsOverview>("analytics", { ...filters }),
    recommendations: ({ gameId, campaignId, teamId }) =>
      call<Recommendations>("community_recommendations", { game_id: gameId ?? null, campaign_id: campaignId ?? null, team_id: teamId ?? null }),
    addGame: async (pin, data) => (await call<{ game_id: number }>("add_game", data, pin)).game_id,
    updateGame: async (pin, gameId, fields) => {
      await call("update_game", { game_id: gameId, fields }, pin);
    },
    addCampaign: async (pin, data) => (await call<{ campaign_id: number }>("add_campaign", data, pin)).campaign_id,
    updateCampaign: async (pin, campaignId, fields) => {
      await call("update_campaign", { campaign_id: campaignId, fields }, pin);
    },
    archivePost: async (pin, postId, archived) => {
      await call("archive_post", { post_id: postId, archived }, pin);
    },
    inbox: (viewer, pin) => call("inbox", "admin" in viewer ? { admin: true } : { user_id: viewer.userId }, pin),
    inboxRead: async (viewer, ids, pin) =>
      (await call<{ marked: number }>("inbox_read", { ...("admin" in viewer ? { admin: true } : { user_id: viewer.userId }), ids }, pin)).marked,
    setSecret: (pin, name, value) => call("set_secret", { name, value }, pin),
    clearSecret: (pin, name) => call("clear_secret", { name }, pin),
    testEmail: async (pin, to) => {
      await call("test_email", { to }, pin);
    },
    testTeams: async (pin) => {
      await call("test_teams", {}, pin);
    },
    systemOverview: (pin, action) => call<SystemOverview>("system_overview", action ? { action } : {}, pin),
    runJob: (pin, name) => call("run_job", { name }, pin),
    retryFailed: (pin) => call("retry_failed", {}, pin),
    backup: (pin) => call("backup", {}, pin),
    exportData: (pin, format) => call("export", { format }, pin),
    search: (query, userId) => call<SearchResults>("search", { query, user_id: userId }),
    seedDemo: (pin) => call("seed_demo", {}, pin),
    retention: (pin) => call("retention", {}, pin),
    metricsText: async () => (await call<{ text: string }>("metrics")).text,
  };
}

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function createTauriTransport(): Promise<EngineTransport> {
  const { invoke } = await import("@tauri-apps/api/core");
  return {
    invoke: (command, args) => invoke(command, { payload: args.payload, pin: args.pin }),
  };
}
