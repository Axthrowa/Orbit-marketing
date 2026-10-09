import { Pencil } from "lucide-react";
import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import { daysText, errorMessage, formatCount, formatDateTime, userStatusView } from "../lib/format";
import { useAdmin } from "../state/AdminContext";
import { useEngine } from "../state/EngineContext";
import type { PersonRow, Role } from "../types";
import { Alert, Avatar, Badge, Button, Card, EmptyState, Field } from "./ui";

const ROLE_LABEL: Record<Role, string> = { admin: "Yönetici", manager: "Ekip yöneticisi", member: "Üye", viewer: "İzleyici (salt okunur)" };

export function TeamPerformance() {
  const { state, teamFilter } = useEngine();
  const [editing, setEditing] = useState<PersonRow | null>(null);

  const groups = useMemo(() => {
    const map = new Map<string, { name: string; people: PersonRow[]; chat: boolean }>();
    for (const team of state?.teams ?? []) {
      if (teamFilter !== null && team.id !== teamFilter) continue;
      map.set(`t${team.id}`, { name: team.name, people: [], chat: team.chat_id !== null });
    }
    for (const person of state?.people ?? []) {
      const key = person.team_id === null ? "none" : `t${person.team_id}`;
      if (!map.has(key)) {
        if (person.team_id !== null || teamFilter !== null) continue;
        map.set(key, { name: "Ekipsiz", people: [], chat: false });
      }
      map.get(key)?.people.push(person);
    }
    return [...map.values()];
  }, [state, teamFilter]);

  if (state === null) return <p className="muted">Yükleniyor…</p>;

  return (
    <div className="stack">
      {groups.length === 0 ? (
        <Card>
          <EmptyState title="Henüz ekip yok">Aşağıdan bir ekip ve kişi ekleyin (yönetici PIN’i gerekir).</EmptyState>
        </Card>
      ) : null}
      {groups.map((group) => (
        <Card
          key={group.name}
          kicker="Ekibin ritmi"
          lift={false}
          title={
            <span className="flex items-center gap-2">
              {group.name}
              <span className="muted font-normal">{group.people.length} kişi</span>
              {group.name !== "Ekipsiz" ? (
                <Badge tone={group.chat ? "success" : "neutral"} title="Ekip yöneticilerinin Telegram sohbeti">
                  {group.chat ? "Telegram grubu tanımlı" : "Telegram grubu yok"}
                </Badge>
              ) : null}
            </span>
          }
          flush
        >
          {group.people.length === 0 ? (
            <EmptyState title="Bu ekipte kullanıcı yok" />
          ) : (
            <PeopleTable people={group.people} onEdit={setEditing} />
          )}
        </Card>
      ))}
      <AdminForms />
      {editing ?<UserEditor person={editing} onClose={() => setEditing(null)} /> : null}
    </div>
  );
}

function PeopleTable({ people, onEdit }: { people: PersonRow[]; onEdit: (person: PersonRow) => void }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Kişi</th>
            <th className="num">Gönderi</th>
            <th className="num">Etkileşim katkısı</th>
            <th className="num">İzlenme</th>
            <th>Son paylaşım</th>
            <th>Uyarı</th>
            <th>Durum</th>
            <th aria-label="İşlemler" />
          </tr>
        </thead>
        <tbody>
          {people.map((person) => {
            const status = userStatusView(person.status);
            const overdue = person.days_since_last_post !== null && person.days_since_last_post >= person.inactivity_days;
            return (
              <tr key={person.id}>
                <td>
                  <span className="person-cell">
                    <Avatar name={person.name} />
                    <span>
                      {person.name}
                      <small>
                        {ROLE_LABEL[person.role]}
                        {person.has_telegram ? "" : " · Telegram yok"}
                      </small>
                    </span>
                  </span>
                </td>
                <td className="num">{formatCount(person.posts)}</td>
                <td className="num" title={person.engagement === null ? "Henüz ölçüm yok" : undefined}>
                  {formatCount(person.engagement)}
                </td>
                <td className="num">{formatCount(person.views)}</td>
                <td>
                  <span style={overdue ? { color: "var(--warning)" } : undefined}>{daysText(person.days_since_last_post)}</span>
                  <div className="muted text-[11px]">eşik: {person.inactivity_days} gün</div>
                </td>
                <td>
                  <StrikeDots count={person.strike_count} max={person.max_strikes} />
                  <div className="muted text-[11px]">
                    {person.strike_count}/{person.max_strikes}
                    {person.total_strikes > person.strike_count ? ` · toplam ${person.total_strikes}` : ""}
                  </div>
                </td>
                <td>
                  <Badge tone={status.tone}>{status.label}</Badge>
                  {person.flagged_at ? <div className="muted text-[11px]">{formatDateTime(person.flagged_at)}</div> : null}
                </td>
                <td>
                  <Button small variant="ghost" aria-label={`${person.name} düzenle`} title="Düzenle (yönetici)" onClick={() => onEdit(person)}>
                    <Pencil size={12} aria-hidden />
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StrikeDots({ count, max }: { count: number; max: number }) {
  return (
    <span className="inline-flex gap-1" role="img" aria-label={`${count}/${max} uyarı`}>
      {Array.from({ length: max }, (_, i) => (
        <span
          key={i}
          style={{
            width: 9,
            height: 9,
            borderRadius: 999,
            background: i < count ? (count >= max ? "var(--danger)" : "var(--warning)") : "var(--surface-2)",
            border: "1px solid var(--line)",
          }}
        />
      ))}
    </span>
  );
}

function AdminForms() {
  const { engine, state, reload, toast } = useEngine();
  const admin = useAdmin();
  const [teamName, setTeamName] = useState("");
  const [teamChat, setTeamChat] = useState("");
  const [userName, setUserName] = useState("");
  const [userTeam, setUserTeam] = useState("");
  const [userRole, setUserRole] = useState<Role>("member");
  const [userChat, setUserChat] = useState("");
  const [userEmail, setUserEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  const addTeam = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const id = await admin.run("Ekip eklemek için yönetici doğrulaması gerekir", (pin) =>
        engine.addTeam(pin, teamName, teamChat),
      );
      if (id !== null) {
        toast("success", `Ekip eklendi: ${teamName}`);
        setTeamName("");
        setTeamChat("");
        await reload();
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  };

  const addUser = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const id = await admin.run("Kullanıcı eklemek için yönetici doğrulaması gerekir", (pin) =>
        engine.addUser(pin, { name: userName, teamId: userTeam === "" ? null : Number(userTeam), role: userRole, telegramId: userChat, email: userEmail.trim() }),
      );
      if (id !== null) {
        toast("success", `Kullanıcı eklendi: ${userName}`);
        setUserName("");
        setUserChat("");
        setUserEmail("");
        await reload();
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="analysis-grid">
        <Card kicker="Yeni ekip" title="Ekip ekle" icon="management">
          <form onSubmit={(event) => void addTeam(event)} className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Ekip adı" htmlFor="team-name">
                <input id="team-name" className="input" value={teamName} onChange={(event) => setTeamName(event.target.value)} placeholder="Marketing A" />
              </Field>
              <Field label="Yönetici Telegram sohbet kimliği" htmlFor="team-chat" hint="Opsiyonel; grup kimlikleri “-” ile başlar.">
                <input id="team-chat" className="input" inputMode="numeric" value={teamChat} onChange={(event) => setTeamChat(event.target.value)} />
              </Field>
            </div>
            <div>
              <Button type="submit" variant="primary" disabled={!teamName.trim()}>
                Ekip ekle
              </Button>
            </div>
          </form>
        </Card>
        <Card kicker="Ekibe kişi ekle" title="Kullanıcı ekle" icon="profile">
          <form onSubmit={(event) => void addUser(event)} className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Ad" htmlFor="user-name">
                <input id="user-name" className="input" value={userName} onChange={(event) => setUserName(event.target.value)} />
              </Field>
              <Field label="Ekip" htmlFor="user-team">
                <select id="user-team" className="select" value={userTeam} onChange={(event) => setUserTeam(event.target.value)}>
                  <option value="">Ekipsiz</option>
                  {(state?.teams ?? []).map((team) => (
                    <option key={team.id} value={team.id}>
                      {team.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Rol" htmlFor="user-role">
                <select id="user-role" className="select" value={userRole} onChange={(event) => setUserRole(event.target.value as Role)}>
                  {(Object.keys(ROLE_LABEL) as Role[]).map((role) => (
                    <option key={role} value={role}>
                      {ROLE_LABEL[role]}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Telegram kullanıcı kimliği" htmlFor="user-chat" hint="Uyarılar buraya gider; kişi botla önce konuşmalı.">
                <input id="user-chat" className="input" inputMode="numeric" value={userChat} onChange={(event) => setUserChat(event.target.value)} />
              </Field>
              <Field label="E-posta" htmlFor="user-email" hint="E-posta kanalı açıksa uyarılar buraya da gider.">
                <input id="user-email" className="input" type="email" value={userEmail} onChange={(event) => setUserEmail(event.target.value)} />
              </Field>
            </div>
            <div>
              <Button type="submit" variant="primary" disabled={!userName.trim()}>
                Kullanıcı ekle
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}

function UserEditor({ person, onClose }: { person: PersonRow; onClose: () => void }) {
  const { engine, state, reload, toast } = useEngine();
  const admin = useAdmin();
  const [team, setTeam] = useState(person.team_id === null ? "" : String(person.team_id));
  const [role, setRole] = useState<Role>(person.role);
  const [chat, setChat] = useState("");
  const [email, setEmail] = useState("");
  const [active, setActive] = useState(person.status !== "inactive");
  const [error, setError] = useState<string | null>(null);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const fields: Record<string, unknown> = {
      team_id: team === "" ? null : Number(team),
      role,
      status: active ? "active" : "inactive",
    };
    if (chat.trim() !== "") fields.telegram_id = chat.trim();
    if (email.trim() !== "") fields.email = email.trim();
    try {
      const done = await admin.run(`${person.name} kullanıcısını düzenlemek için yönetici doğrulaması gerekir`, (pin) =>
        engine.updateUser(pin, person.id, fields),
      );
      if (done !== null) {
        toast("success", `${person.name} güncellendi`);
        await reload();
        onClose();
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  };

  return (
    <>
      <div className="drawer-scrim" style={{ zIndex: 50 }} onClick={onClose} aria-hidden />
      <form className="modal" onSubmit={(event) => void save(event)} aria-label={`${person.name} düzenle`}>
        <div className="card-head">
          <h2 className="card-title m-0">{person.name}</h2>
        </div>
        <div className="card-body flex flex-col gap-3">
          <Field label="Ekip" htmlFor="edit-team">
            <select id="edit-team" className="select" value={team} onChange={(event) => setTeam(event.target.value)}>
              <option value="">Ekipsiz</option>
              {(state?.teams ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Rol" htmlFor="edit-role">
            <select id="edit-role" className="select" value={role} onChange={(event) => setRole(event.target.value as Role)}>
              {(Object.keys(ROLE_LABEL) as Role[]).map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Telegram kullanıcı kimliği" htmlFor="edit-chat" hint={person.has_telegram ? "Tanımlı; değiştirmek için yeni kimlik girin." : "Henüz tanımlı değil."}>
            <input id="edit-chat" className="input" inputMode="numeric" value={chat} onChange={(event) => setChat(event.target.value)} />
          </Field>
          <Field label="E-posta" htmlFor="edit-email" hint={person.has_email ? "Tanımlı; değiştirmek için yeni adres girin." : "Henüz tanımlı değil."}>
            <input id="edit-email" className="input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </Field>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
            Aktif (pasif kullanıcıya uyarı gitmez)
          </label>
          {person.status === "flagged" ? (
            <Alert tone="danger">Kullanıcı işaretli. Yeni geçerli bir paylaşım eklenince uyarılar otomatik sıfırlanır; geçmiş kayıtlar korunur.</Alert>
          ) : null}
          {error ? <Alert tone="danger">{error}</Alert> : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              Vazgeç
            </Button>
            <Button variant="primary" type="submit">
              Kaydet
            </Button>
          </div>
        </div>
      </form>
    </>
  );
}
