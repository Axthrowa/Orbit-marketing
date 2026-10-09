// Orbit'in özgün çizgi simgeleri (Orbit Marketing Web v0.3.0 icons.js): 24px ızgara, yumuşak köşeler.
const PATHS = {
  overview: (
    <>
      <rect x="3" y="3" width="7" height="8" rx="2" />
      <rect x="14" y="3" width="7" height="5" rx="2" />
      <rect x="3" y="15" width="7" height="6" rx="2" />
      <rect x="14" y="12" width="7" height="9" rx="2" />
    </>
  ),
  shares: (
    <path
      d="m9 15 6-6M8 17l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0M16 7l1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"
      transform="scale(.92)"
    />
  ),
  audience: (
    <>
      <path d="M20 11a8 8 0 0 1-8 8H6l-4 3 1-6a8 8 0 1 1 17-5Z" />
      <path d="M7 9h9M7 13h6" />
    </>
  ),
  connections: <path d="m8 3 1 5M16 3l-1 5M6 8h12v3a6 6 0 0 1-12 0ZM12 17v4" />,
  management: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3 21v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M17 15a5 5 0 0 1 4 5" />
    </>
  ),
  communities: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m15 8-2 6-5 2 2-6Z" />
    </>
  ),
  campaigns: <path d="M3 11v4l14 4V5ZM7 16l2 5M21 8v8" />,
  profile: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </>
  ),
  bell: <path d="M5 16h14l-2-3V9a5 5 0 0 0-10 0v4ZM10 20h4M12 2v2" />,
  system: (
    <>
      <rect x="3" y="4" width="18" height="6" rx="2" />
      <rect x="3" y="14" width="18" height="6" rx="2" />
      <path d="M7 7h.01M7 17h.01M11 7h6M11 17h6" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4-4" />
    </>
  ),
  arrow: <path d="M5 19 19 5M5 5h14v14" />,
  refresh: <path d="M20 11a8 8 0 1 0-3 7M20 4v7h-7" />,
  download: <path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4" />,
  heart: <path d="M12 20 3.5 12A5 5 0 0 1 12 5a5 5 0 0 1 8.5 7Z" />,
  chart: <path d="M4 4v16h17M8 15l4-5 4 3 5-7" />,
  orbit: (
    <>
      <ellipse cx="12" cy="12" rx="10" ry="5" transform="rotate(-32 12 12)" />
      <ellipse cx="12" cy="12" rx="10" ry="5" transform="rotate(40 12 12)" />
      <circle cx="12" cy="12" r="2" />
    </>
  ),
} as const;

export type OrbitIconName = keyof typeof PATHS;

export function OrbitIcon({ name, label }: { name: OrbitIconName; label?: string }) {
  return (
    <svg
      className="orbit-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {PATHS[name]}
    </svg>
  );
}
