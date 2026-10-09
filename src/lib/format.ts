import type { DataStatus, Recommendation, Tone, UserStatus } from "../types";

const NUMBER = new Intl.NumberFormat("tr-TR");
const DASH = "—";

/** Bilinmeyen (null) değer "—" olur; 0 gerçek sıfırdır. */
export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? DASH : NUMBER.format(value);
}

export function formatPercent(ratio: number | null | undefined): string {
  return ratio === null || ratio === undefined ? DASH : `%${Math.round(ratio * 100)}`;
}

export function parseIso(iso: string): Date {
  return new Date(iso);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = parseIso(iso);
  return date.toLocaleString("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return parseIso(iso).toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric" });
}

export function formatClock(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return parseIso(iso).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

export function timeAgo(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "hiç";
  const minutes = Math.floor((now.getTime() - parseIso(iso).getTime()) / 60_000);
  if (minutes < 1) return "az önce";
  if (minutes < 60) return `${minutes} dk önce`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} sa önce`;
  return `${Math.floor(hours / 24)} gün önce`;
}

export function daysText(days: number | null): string {
  if (days === null) return "hiç paylaşım yok";
  if (days === 0) return "bugün";
  return `${days} gün önce`;
}

export function shortUrl(url: string, max = 44): string {
  const stripped = url.replace(/^https?:\/\/(www\.)?/, "");
  return stripped.length > max ? `${stripped.slice(0, max - 1)}…` : stripped;
}

export function sentimentScore(positive: number | null, negative: number | null): number | null {
  if (positive === null || negative === null) return null;
  return Math.round((positive - negative) * 100);
}

export interface StatusView {
  tone: Tone;
  label: string;
}

export function dataStatusView(status: DataStatus): StatusView {
  switch (status) {
    case "OK":
      return { tone: "success", label: "Güncel" };
    case "MANUAL":
      return { tone: "info", label: "Elle girildi" };
    case "DATA_UNAVAILABLE":
      return { tone: "warning", label: "Veri alınamıyor" };
    case "AUTHORIZATION_REQUIRED":
      return { tone: "warning", label: "Giriş gerekli" };
    case "PENDING":
      return { tone: "neutral", label: "Bekliyor" };
  }
}

export function userStatusView(status: UserStatus): StatusView {
  switch (status) {
    case "active":
      return { tone: "success", label: "Aktif" };
    case "flagged":
      return { tone: "danger", label: "İNCELEME GEREKLİ" };
    case "inactive":
      return { tone: "neutral", label: "Pasif" };
  }
}

export function recommendationView(rec: Recommendation): StatusView {
  switch (rec) {
    case "CLEAN":
      return { tone: "success", label: "Temiz" };
    case "SAFE":
      return { tone: "success", label: "Güvenli" };
    case "CAUTION":
      return { tone: "warning", label: "Dikkat" };
    case "RECENTLY_USED":
      return { tone: "warning", label: "Yakın zamanda kullanıldı" };
    case "AVOID":
      return { tone: "danger", label: "Kaçının" };
  }
}

/** Kullanıcıya gösterilecek hata UX'i: 0 göstermek yerine durumu ve son başarılı zamanı söyler. */
export function unavailableMessage(
  platform: string,
  status: DataStatus,
  lastSuccess: string | null,
): string | null {
  if (status !== "DATA_UNAVAILABLE" && status !== "AUTHORIZATION_REQUIRED") return null;
  const last = lastSuccess ? `Son başarılı güncelleme: ${formatClock(lastSuccess)}` : "Henüz başarılı ölçüm yok";
  const reason =
    status === "AUTHORIZATION_REQUIRED"
      ? `${platform} verileri için oturum açılması gerekiyor.`
      : `${platform} verileri şu anda alınamıyor.`;
  return `${reason} ${last}`;
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Beklenmeyen hata";
}
