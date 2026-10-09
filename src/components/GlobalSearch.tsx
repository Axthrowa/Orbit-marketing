import { useEffect, useRef, useState } from "react";

import { errorMessage, shortUrl } from "../lib/format";
import { useEngine } from "../state/EngineContext";
import type { SearchResults } from "../types";
import { OrbitIcon } from "./OrbitIcon";
import { PlatformLogo } from "./PlatformLogo";

const DEBOUNCE_MS = 250;

export type SearchTarget = { kind: "post"; id: number } | { kind: "person" } | { kind: "community"; name: string } | { kind: "campaign" } | { kind: "game" };

/** Üst başlıktaki genel arama: paylaşım, kişi, topluluk, kampanya ve oyun. Kullanıcı hesabında yalnız kendi paylaşımları. */
export function GlobalSearch({ userId, onPick }: { userId: number | null; onPick: (target: SearchTarget) => void }) {
  const { engine } = useEngine();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setResults(null);
      setError(null);
      return;
    }
    let alive = true;
    const timer = window.setTimeout(() => {
      engine
        .search(q, userId)
        .then((r) => {
          if (!alive) return;
          setResults(r);
          setError(null);
        })
        .catch((caught: unknown) => {
          if (alive) setError(errorMessage(caught));
        });
    }, DEBOUNCE_MS);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [engine, query, userId]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const pick = (target: SearchTarget) => {
    onPick(target);
    setOpen(false);
    setQuery("");
  };

  const total = results
    ? results.posts.length + results.people.length + results.communities.length + results.campaigns.length + results.games.length
    : 0;

  return (
    <div className="global-search" ref={box}>
      <OrbitIcon name="search" />
      <input
        className="input"
        type="search"
        aria-label="Ara"
        placeholder="Ara: link, not, kişi, topluluk…"
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && query.trim().length >= 2 ? (
        <div className="search-results" role="listbox" aria-label="Arama sonuçları">
          {error ? <p className="muted">{error}</p> : null}
          {results && total === 0 ? <p className="muted">Sonuç yok</p> : null}
          {results?.posts.map((p) => (
            <button key={`p${p.id}`} role="option" aria-selected={false} onClick={() => pick({ kind: "post", id: p.id })}>
              <PlatformLogo platform={p.platform} size={14} />
              <span>
                {shortUrl(p.url, 40)}
                <small>
                  {p.user_name}
                  {p.community_name ? ` · ${p.community_name}` : ""}
                  {p.note ? ` · ${p.note}` : ""}
                </small>
              </span>
            </button>
          ))}
          {results?.people.map((p) => (
            <button key={`u${p.id}`} role="option" aria-selected={false} onClick={() => pick({ kind: "person" })}>
              <OrbitIcon name="profile" />
              <span>
                {p.name}
                <small>Kişi · {p.team_name ?? "Ekipsiz"}</small>
              </span>
            </button>
          ))}
          {results?.communities.map((c) => (
            <button key={`c${c.id}`} role="option" aria-selected={false} onClick={() => pick({ kind: "community", name: c.name })}>
              <PlatformLogo platform={c.platform} size={14} />
              <span>
                {c.name}
                <small>Topluluk</small>
              </span>
            </button>
          ))}
          {results?.campaigns.map((c) => (
            <button key={`k${c.id}`} role="option" aria-selected={false} onClick={() => pick({ kind: "campaign" })}>
              <OrbitIcon name="campaigns" />
              <span>
                {c.name}
                <small>Kampanya</small>
              </span>
            </button>
          ))}
          {results?.games.map((g) => (
            <button key={`g${g.id}`} role="option" aria-selected={false} onClick={() => pick({ kind: "game" })}>
              <OrbitIcon name="campaigns" />
              <span>
                {g.name}
                <small>Oyun</small>
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
