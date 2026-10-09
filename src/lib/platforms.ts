// Yalnızca GÖRÜNTÜ içindir (link yazılırken logo önizlemesi). Asıl tanıma ve doğrulama motordadır
// (engine/etkilesim/platforms.py + security.py).
import type { Platform } from "../types";

const HOSTS: [RegExp, Platform][] = [
  [/(^|\.)(x|twitter)\.com$/, "X"],
  [/(^|\.)instagram\.com$/, "Instagram"],
  [/(^|\.)threads\.(net|com)$/, "Threads"],
  [/(^|\.)(facebook\.com|fb\.com|fb\.watch)$/, "Facebook"],
  [/(^|\.)(reddit\.com|redd\.it)$/, "Reddit"],
  [/(^|\.)(youtube\.com|youtu\.be)$/, "YouTube"],
];

export function guessPlatform(url: string): Platform | null {
  let host: string;
  try {
    host = new URL(url.trim()).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return null; // henüz geçerli bir adres değil
  }
  for (const [pattern, platform] of HOSTS) {
    if (pattern.test(host)) return platform;
  }
  return /^(forum|forums|community|discuss)\./.test(host) ? "Forum" : "Other";
}
