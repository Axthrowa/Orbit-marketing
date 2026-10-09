import { useState } from "react";
import type { FormEvent } from "react";

import { errorMessage, formatCount, formatDate } from "../lib/format";
import { useAdmin } from "../state/AdminContext";
import { useEngine } from "../state/EngineContext";
import type { Campaign, CampaignStatus, Game, Tone } from "../types";
import { Badge, Button, Card, EmptyState, Field } from "./ui";

const STATUS: Record<CampaignStatus, { label: string; tone: Tone }> = {
  planned: { label: "Planlandı", tone: "info" },
  active: { label: "Aktif", tone: "success" },
  finished: { label: "Bitti", tone: "neutral" },
  archived: { label: "Arşivde", tone: "neutral" },
};

const splitList = (value: string): string[] =>
  value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);

function GameForm() {
  const { engine, reload, toast } = useEngine();
  const admin = useAdmin();
  const [name, setName] = useState("");
  const [genres, setGenres] = useState("");
  const [languages, setLanguages] = useState("tr, en");
  const [keywords, setKeywords] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const id = await admin.run("Oyun eklemek için yönetici doğrulaması gerekir", (pin) =>
        engine.addGame(pin, { name, genres: splitList(genres), languages: splitList(languages), keywords: splitList(keywords) }),
      );
      if (id !== null) {
        toast("success", `“${name.trim()}” eklendi`);
        setName("");
        setGenres("");
        setKeywords("");
        await reload();
      }
    } catch (caught) {
      toast("danger", errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => void submit(e)}>
      <Field label="Oyun adı" htmlFor="game-name">
        <input id="game-name" className="input" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} required />
      </Field>
      <Field label="Türler" hint="Virgülle ayırın: FPS, RPG" htmlFor="game-genres">
        <input id="game-genres" className="input" value={genres} onChange={(e) => setGenres(e.target.value)} />
      </Field>
      <Field label="Hedef diller" hint="tr, en …" htmlFor="game-langs">
        <input id="game-langs" className="input" value={languages} onChange={(e) => setLanguages(e.target.value)} />
      </Field>
      <Field label="Anahtar kelimeler" hint="Topluluk önerilerinde kullanılır" htmlFor="game-keys">
        <input id="game-keys" className="input" value={keywords} onChange={(e) => setKeywords(e.target.value)} />
      </Field>
      <div className="sm:col-span-2">
        <Button type="submit" variant="primary" icon="campaigns" busy={busy} disabled={!name.trim()}>
          Oyun ekle
        </Button>
      </div>
    </form>
  );
}

function CampaignForm({ games }: { games: Game[] }) {
  const { engine, reload, toast } = useEngine();
  const admin = useAdmin();
  const [name, setName] = useState("");
  const [gameId, setGameId] = useState<number | null>(games[0]?.id ?? null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [status, setStatus] = useState<CampaignStatus>("active");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const id = await admin.run("Kampanya eklemek için yönetici doğrulaması gerekir", (pin) =>
        engine.addCampaign(pin, {
          name,
          game_id: gameId,
          start_date: start || null,
          end_date: end || null,
          status,
          description: description.trim() || null,
        }),
      );
      if (id !== null) {
        toast("success", `“${name.trim()}” kampanyası eklendi`);
        setName("");
        setDescription("");
        await reload();
      }
    } catch (caught) {
      toast("danger", errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => void submit(e)}>
      <Field label="Kampanya adı" htmlFor="camp-name">
        <input id="camp-name" className="input" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} required />
      </Field>
      <Field label="Oyun" htmlFor="camp-game">
        <select id="camp-game" className="input" value={gameId ?? ""} onChange={(e) => setGameId(e.target.value === "" ? null : Number(e.target.value))}>
          <option value="">Oyunsuz</option>
          {games.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Başlangıç" htmlFor="camp-start">
        <input id="camp-start" type="date" className="input" value={start} onChange={(e) => setStart(e.target.value)} />
      </Field>
      <Field label="Bitiş" htmlFor="camp-end">
        <input id="camp-end" type="date" className="input" value={end} onChange={(e) => setEnd(e.target.value)} />
      </Field>
      <Field label="Durum" htmlFor="camp-status">
        <select id="camp-status" className="input" value={status} onChange={(e) => setStatus(e.target.value as CampaignStatus)}>
          {(Object.keys(STATUS) as CampaignStatus[]).map((s) => (
            <option key={s} value={s}>
              {STATUS[s].label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Açıklama" htmlFor="camp-desc">
        <input id="camp-desc" className="input" value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <div className="sm:col-span-2">
        <Button type="submit" variant="primary" icon="campaigns" busy={busy} disabled={!name.trim()}>
          Kampanya ekle
        </Button>
      </div>
    </form>
  );
}

/** Yönetici: oyun ve kampanya kataloğu. Paylaşımlar bunlara bağlanır, analitik bunlarla süzülür. */
export function CampaignsScreen() {
  const { engine, state, reload, toast } = useEngine();
  const admin = useAdmin();
  const games = state?.games ?? [];
  const campaigns = state?.campaigns ?? [];

  const setCampaignStatus = async (campaign: Campaign, status: CampaignStatus) => {
    try {
      const done = await admin.run(`“${campaign.name}” durumunu değiştirmek için yönetici doğrulaması gerekir`, (pin) =>
        engine.updateCampaign(pin, campaign.id, { status }),
      );
      if (done !== null) await reload();
    } catch (caught) {
      toast("danger", errorMessage(caught));
    }
  };

  const toggleGame = async (game: Game) => {
    const status = game.status === "active" ? "archived" : "active";
    try {
      const done = await admin.run(`“${game.name}” oyununu güncellemek için yönetici doğrulaması gerekir`, (pin) =>
        engine.updateGame(pin, game.id, { status }),
      );
      if (done !== null) await reload();
    } catch (caught) {
      toast("danger", errorMessage(caught));
    }
  };

  return (
    <div className="grid gap-5">
      <Card kicker="Kampanyalar" title="Aktif ve planlanan kampanyalar" icon="campaigns">
        {campaigns.length === 0 ? (
          <EmptyState title="Henüz kampanya yok">Aşağıdan ilk kampanyayı ekleyin; paylaşımlar kampanyaya bağlanabilir.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table style={{ minWidth: 820 }}>
              <thead>
                <tr>
                  <th>Kampanya</th>
                  <th>Oyun</th>
                  <th>Tarih</th>
                  <th className="num">Paylaşım</th>
                  <th className="num">Etkileşim</th>
                  <th className="num">İzlenme</th>
                  <th>Durum</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <strong>{c.name}</strong>
                      {c.description ? <small>{c.description}</small> : null}
                    </td>
                    <td>{c.game_name ?? "—"}</td>
                    <td>
                      {c.start_date ? formatDate(c.start_date) : "—"} – {c.end_date ? formatDate(c.end_date) : "süresiz"}
                    </td>
                    <td className="num">{c.posts}</td>
                    <td className="num">{formatCount(c.engagement)}</td>
                    <td className="num">{formatCount(c.views)}</td>
                    <td>
                      <select
                        className="input"
                        aria-label={`${c.name} durumu`}
                        value={c.status}
                        onChange={(e) => void setCampaignStatus(c, e.target.value as CampaignStatus)}
                      >
                        {(Object.keys(STATUS) as CampaignStatus[]).map((s) => (
                          <option key={s} value={s}>
                            {STATUS[s].label}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card kicker="Yeni" title="Kampanya ekle" lift={false}>
          <CampaignForm games={games.filter((g) => g.status === "active")} />
        </Card>
        <Card kicker="Yeni" title="Oyun ekle" lift={false}>
          <GameForm />
        </Card>
      </div>

      <Card kicker="Oyunlar" title="Oyun kataloğu">
        {games.length === 0 ? (
          <EmptyState title="Henüz oyun yok" />
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {games.map((g) => (
              <article key={g.id} className="alert">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <strong>{g.name}</strong>
                    <Badge tone={g.status === "active" ? "success" : "neutral"}>{g.status === "active" ? "Aktif" : "Arşivde"}</Badge>
                  </div>
                  <div className="muted mt-1 text-[11px]">
                    {g.genres.join(", ") || "Tür belirtilmedi"} · {g.languages.join(", ").toUpperCase() || "dil yok"} · {g.posts} paylaşım
                  </div>
                  <div className="mt-2">
                    <Button small onClick={() => void toggleGame(g)}>
                      {g.status === "active" ? "Arşivle" : "Yeniden etkinleştir"}
                    </Button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
