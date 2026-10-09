import { describe, expect, it } from "vitest";

import {
  dataStatusView,
  daysText,
  formatCount,
  formatPercent,
  recommendationView,
  sentimentScore,
  shortUrl,
  timeAgo,
  unavailableMessage,
  userStatusView,
} from "./format";

describe("formatCount", () => {
  it("shows unknown as a dash and a real zero as 0", () => {
    expect(formatCount(null)).toBe("—");
    expect(formatCount(undefined)).toBe("—");
    expect(formatCount(0)).toBe("0");
  });
  it("uses Turkish digit grouping", () => {
    expect(formatCount(6800)).toMatch(/^6\.800$/);
  });
});

describe("formatPercent", () => {
  it("rounds ratios and keeps unknown distinct from zero", () => {
    expect(formatPercent(0.612)).toBe("%61");
    expect(formatPercent(0)).toBe("%0");
    expect(formatPercent(null)).toBe("—");
  });
});

describe("sentimentScore", () => {
  it("is positive minus negative in points", () => {
    expect(sentimentScore(0.61, 0.14)).toBe(47);
    expect(sentimentScore(null, 0.1)).toBeNull();
  });
});

describe("timeAgo / daysText", () => {
  const now = new Date("2026-10-05T12:00:00Z");
  it("formats relative times", () => {
    expect(timeAgo("2026-10-05T11:59:40Z", now)).toBe("az önce");
    expect(timeAgo("2026-10-05T11:30:00Z", now)).toBe("30 dk önce");
    expect(timeAgo("2026-10-05T07:00:00Z", now)).toBe("5 sa önce");
    expect(timeAgo("2026-10-02T12:00:00Z", now)).toBe("3 gün önce");
    expect(timeAgo(null, now)).toBe("hiç");
  });
  it("describes days since last post", () => {
    expect(daysText(null)).toBe("hiç paylaşım yok");
    expect(daysText(0)).toBe("bugün");
    expect(daysText(4)).toBe("4 gün önce");
  });
});

describe("shortUrl", () => {
  it("strips scheme and truncates", () => {
    expect(shortUrl("https://www.x.com/a/status/1")).toBe("x.com/a/status/1");
    expect(shortUrl("https://example.com/" + "a".repeat(80), 20)).toHaveLength(20);
  });
});

describe("status views", () => {
  it("maps data statuses to tones", () => {
    expect(dataStatusView("OK").tone).toBe("success");
    expect(dataStatusView("DATA_UNAVAILABLE").tone).toBe("warning");
    expect(dataStatusView("AUTHORIZATION_REQUIRED").label).toBe("Giriş gerekli");
    expect(dataStatusView("MANUAL").label).toBe("Elle girildi");
  });
  it("flags users that need review loudly", () => {
    expect(userStatusView("flagged")).toEqual({ tone: "danger", label: "İNCELEME GEREKLİ" });
  });
  it("maps every recommendation", () => {
    expect(recommendationView("AVOID").tone).toBe("danger");
    expect(recommendationView("RECENTLY_USED").tone).toBe("warning");
    expect(recommendationView("CLEAN").label).toBe("Temiz");
  });
});

describe("unavailableMessage", () => {
  it("explains the problem instead of showing zeros", () => {
    const text = unavailableMessage("Instagram", "DATA_UNAVAILABLE", "2026-10-05T11:20:00Z");
    expect(text).toContain("Instagram verileri şu anda alınamıyor.");
    expect(text).toContain("Son başarılı güncelleme:");
  });
  it("says so when there was never a success, and stays silent when data is fine", () => {
    expect(unavailableMessage("X", "AUTHORIZATION_REQUIRED", null)).toContain("Henüz başarılı ölçüm yok");
    expect(unavailableMessage("X", "OK", null)).toBeNull();
    expect(unavailableMessage("X", "MANUAL", null)).toBeNull();
  });
});
