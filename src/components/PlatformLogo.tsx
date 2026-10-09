// Platformların resmî logoları (simple-icons, CC0). Derleme sırasında gömülür; dış istek yapılmaz.
// Logolar yalnızca platformu tanımlamak için kullanılır; marka hakları sahiplerine aittir.
import { siDiscourse, siFacebook, siInstagram, siReddit, siTelegram, siThreads, siX, siYoutube } from "simple-icons";
import type { SimpleIcon } from "simple-icons";

import { OrbitIcon } from "./OrbitIcon";

const ICONS: Record<string, SimpleIcon> = {
  X: siX,
  Instagram: siInstagram,
  Facebook: siFacebook,
  Threads: siThreads,
  Reddit: siReddit,
  YouTube: siYoutube,
  Discourse: siDiscourse,
  Telegram: siTelegram,
};

/** Siyah logolar karanlık temada metin rengine döner; Instagram resmî gradyanıyla çizilir. */
function fillFor(name: string, icon: SimpleIcon): string {
  if (name === "Instagram") return "url(#instagram-gradient)";
  return icon.hex === "000000" ? "var(--ink)" : `#${icon.hex}`;
}

export function PlatformLogo({ platform, size = 18, withName = false }: { platform: string; size?: number; withName?: boolean }) {
  const icon = ICONS[platform];
  const label = platform === "Other" ? "Diğer" : platform;
  return (
    <span className="platform-logo" title={label}>
      {icon ? (
        <svg viewBox="0 0 24 24" width={size} height={size} role="img" aria-label={label}>
          {platform === "Instagram" ? (
            <defs>
              <radialGradient id="instagram-gradient" cx="30%" cy="107%" r="150%">
                <stop offset="0" stopColor="#fdf497" />
                <stop offset="0.05" stopColor="#fdf497" />
                <stop offset="0.45" stopColor="#fd5949" />
                <stop offset="0.6" stopColor="#d6249f" />
                <stop offset="0.9" stopColor="#285AEB" />
              </radialGradient>
            </defs>
          ) : null}
          <path d={icon.path} fill={fillFor(platform, icon)} />
        </svg>
      ) : (
        <span className="platform-logo-generic" style={{ width: size, height: size }} role="img" aria-label={label}>
          <OrbitIcon name={platform === "Forum" ? "audience" : "shares"} />
        </span>
      )}
      {withName ? <span className="platform-logo-name">{label}</span> : null}
    </span>
  );
}
