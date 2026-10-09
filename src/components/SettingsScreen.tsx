import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { errorMessage } from "../lib/format";
import { useAdmin } from "../state/AdminContext";
import { useEngine } from "../state/EngineContext";
import type { SettingSpec, SettingValue, SettingsView } from "../types";
import { PlatformLogo } from "./PlatformLogo";
import { Alert, Badge, Button, Card, Field } from "./ui";

interface Group {
  kicker: string;
  title: string;
  description: string;
  keys: string[];
}

const GROUPS: Group[] = [
  {
    kicker: "İstikrar için küçük hatırlatmalar",
    title: "Hatırlatma ve uyarı (strike) kuralları",
    description:
      "Kullanıcı kaç gün paylaşım yapmazsa uyarılsın, uyarılar hangi aralıkla gitsin ve kaçıncı uyarıda yönetici incelemesine düşsün.",
    keys: ["inactivity_days", "strike_interval_hours", "max_strikes", "strike_check_time"],
  },
  {
    kicker: "Doğru topluluklar",
    title: "Topluluk tekrar paylaşım eşikleri",
    description: "Aynı topluluğa son paylaşımdan bu yana geçen gün sayısına göre KAÇIN / YAKIN ZAMANDA / DİKKAT uyarısı verilir.",
    keys: ["community_avoid_days", "community_recent_days", "community_caution_days"],
  },
  {
    kicker: "Ölçüm",
    title: "Ölçüm ve duygu analizi",
    description: "Linklerin ne sıklıkla ölçüleceği ve yorumların nasıl analiz edileceği.",
    keys: ["metrics_interval_hours", "metrics_schedule", "comment_limit", "scrape_enabled", "scrape_headless", "sentiment_engine"],
  },
  {
    kicker: "Radar",
    title: "Topluluk keşfi",
    description: "Radar’ın hangi anahtar kelimelerle, ne sıklıkla topluluk arayacağı.",
    keys: ["discovery_enabled", "discovery_interval_hours", "discovery_keywords", "target_languages"],
  },
  {
    kicker: "Lider tablosu",
    title: "Performans puanı ağırlıkları",
    description: "Her bileşenin puandaki payı. Toplamın 100 olması gerekmez; motor oranlara göre normalize eder.",
    keys: [
      "perf_weight_consistency",
      "perf_weight_engagement",
      "perf_weight_sentiment",
      "perf_weight_diversity",
      "perf_weight_velocity",
      "perf_weight_campaign",
    ],
  },
  {
    kicker: "Veri yaşam döngüsü",
    title: "Saklama ve yedekleme",
    description: "Eski yorum metinleri ve denetim kayıtları bu sürelerden sonra temizlenir (sayılar ve geçmiş kalır). Yedek her gece alınır.",
    keys: ["comment_retention_days", "audit_retention_days", "backup_keep"],
  },
  {
    kicker: "Bildirim kanalı",
    title: "Telegram bildirimleri",
    description: "Kapalıyken hiçbir mesaj gitmez; açıldığında önceden biriken uyarılar toplu gönderilmez.",
    keys: ["notifications_enabled", "admin_chat_id"],
  },
  {
    kicker: "Bildirim kanalı",
    title: "E-posta ve Microsoft Teams",
    description: "Uyarılar seçilen her kanala ayrı ayrı gider. SMTP parolası ve Teams webhook adresi aşağıdaki kartta, kimlik deposunda saklanır.",
    keys: ["email_enabled", "smtp_host", "smtp_port", "smtp_user", "smtp_from", "admin_email", "teams_enabled"],
  },
];

export function SettingsScreen() {
  const { state } = useEngine();
  return (
    <div className="stack">
      <RulesEditor />
      <TelegramCard tokenSet={state?.security.telegram_token_set ?? false} />
      <ChannelSecretsCard secrets={state?.security.secrets ?? {}} />
      <SessionsCard />
      <OperationsCard />
      <PinCard pinSet={state?.security.pin_set ?? false} />
      <About />
    </div>
  );
}

function RulesEditor() {
  const { engine, state, reload, toast } = useEngine();
  const admin = useAdmin();
  const [scope, setScope] = useState<number | null>(null);
  const [view, setView] = useState<SettingsView | null>(null);
  const [draft, setDraft] = useState<Record<string, SettingValue>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const loaded = await engine.settingsGet(scope);
      setView(loaded);
      setDraft(loaded.values);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [engine, scope]);

  useEffect(() => {
    void load();
  }, [load]);

  const specs = useMemo(() => new Map((view?.spec ?? []).map((s) => [s.key, s])), [view]);
  const teams = state?.teams ?? [];

  const changes = useMemo(() => {
    const out: Record<string, SettingValue> = {};
    if (!view) return out;
    for (const [key, value] of Object.entries(draft)) {
      const spec = specs.get(key);
      if (!spec || (scope !== null && !spec.team_overridable)) continue;
      if (JSON.stringify(value) !== JSON.stringify(view.values[key])) out[key] = value;
    }
    return out;
  }, [draft, view, specs, scope]);

  const save = async () => {
    const invalid = Object.entries(changes)
      .map(([key, value]) => ({ spec: specs.get(key), value }))
      .find(({ spec, value }) => spec?.kind === "int" && (typeof value !== "number" || !Number.isInteger(value) || value < spec.low || value > spec.high));
    if (invalid?.spec) {
      setError(`${invalid.spec.label}: ${invalid.spec.low}–${invalid.spec.high} arasında bir tam sayı girin`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const done = await admin.run("Ayarları kaydetmek için yönetici doğrulaması gerekir", (pin) =>
        engine.settingsSet(pin, changes, scope),
      );
      if (done !== null) {
        toast("success", "Ayarlar kaydedildi; zamanlama bir dakika içinde güncellenir");
        await load();
        await reload();
      }
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const clearOverride = async (key: string) => {
    if (scope === null) return;
    try {
      const done = await admin.run("Ekip ayarını kaldırmak için yönetici doğrulaması gerekir", (pin) =>
        engine.settingsClearOverride(pin, key, scope),
      );
      if (done !== null) {
        await load();
        await reload();
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  };

  if (!view) return error ? <Alert tone="danger">{error}</Alert> : <div className="muted">Yükleniyor…</div>;

  return (
    <>
      <Card
        title="Ayar kapsamı"
        actions={
          <select className="select" style={{ width: 220 }} aria-label="Ayar kapsamı" value={scope === null ? "" : String(scope)} onChange={(event) => setScope(event.target.value === "" ? null : Number(event.target.value))}>
            <option value="">Genel (tüm ekipler)</option>
            {teams.map((team) => (
              <option key={team.id} value={team.id}>
                Ekip: {team.name}
              </option>
            ))}
          </select>
        }
      >
        <div className="muted">
          {scope === null
            ? "Genel değerler tüm ekipler için varsayılandır."
            : "Ekip bazında yalnızca uyarı kuralları değiştirilebilir. Değiştirmediğiniz ayar genel değeri kullanır."}
        </div>
      </Card>
      {error ? <Alert tone="danger">{error}</Alert> : null}
      {GROUPS.map((group) => {
        const visible = group.keys.map((k) => specs.get(k)).filter((s): s is SettingSpec => s !== undefined && (scope === null || s.team_overridable));
        if (visible.length === 0) return null;
        return (
          <Card key={group.title} kicker={group.kicker} title={group.title}>
            <p className="muted mb-3 mt-0">{group.description}</p>
            <div className="grid gap-4 sm:grid-cols-2">
              {visible.map((spec) => (
                <SettingInput
                  key={spec.key}
                  spec={spec}
                  value={draft[spec.key]}
                  overridden={scope !== null && spec.key in view.overrides}
                  onChange={(value) => setDraft({ ...draft, [spec.key]: value })}
                  onClear={() => void clearOverride(spec.key)}
                />
              ))}
            </div>
          </Card>
        );
      })}
      <div className="sticky bottom-0 flex items-center justify-between gap-3 border-t border-line bg-bg py-3">
        <span className="muted">{Object.keys(changes).length === 0 ? "Değişiklik yok" : `${Object.keys(changes).length} değişiklik kaydedilmeyi bekliyor`}</span>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setDraft(view.values)} disabled={Object.keys(changes).length === 0}>
            Geri al
          </Button>
          <Button variant="primary" busy={busy} disabled={Object.keys(changes).length === 0} onClick={() => void save()}>
            Ayarları kaydet
          </Button>
        </div>
      </div>
    </>
  );
}

const CHOICE_LABEL: Record<string, string> = {
  lexicon: "Kural tabanlı (TR/EN, yerel)",
  transformer: "Transformer (yerelde model varsa)",
  fixed: "Sabit aralık",
  adaptive: "Uyarlanabilir (yeni paylaşım sık, eski seyrek)",
};

function SettingInput({
  spec,
  value,
  overridden,
  onChange,
  onClear,
}: {
  spec: SettingSpec;
  value: SettingValue | undefined;
  overridden: boolean;
  onChange: (value: SettingValue) => void;
  onClear: () => void;
}) {
  const id = `set-${spec.key}`;
  const hint = spec.kind === "int" ? `${spec.low}–${spec.high}` : undefined;
  let control;
  if (spec.kind === "bool") {
    control = (
      <label className="flex items-center gap-2" htmlFor={id}>
        <input id={id} type="checkbox" checked={value === true} onChange={(event) => onChange(event.target.checked)} />
        {value === true ? "Açık" : "Kapalı"}
      </label>
    );
  } else if (spec.kind === "int") {
    control = (
      // Düzenlerken boş bırakılabilir (""), kaydetmeden önce doğrulanır; değer alt sınıra zıplamaz.
      <input id={id} className="input" type="number" min={spec.low} max={spec.high} value={typeof value === "number" ? value : ""} onChange={(event) => onChange(event.target.value === "" ? "" : Number(event.target.value))} />
    );
  } else if (spec.kind === "time") {
    control = <input id={id} className="input" type="time" value={typeof value === "string" ? value : "00:00"} onChange={(event) => onChange(event.target.value)} />;
  } else if (spec.kind === "enum") {
    control = (
      <select id={id} className="select" value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)}>
        {spec.choices.map((choice) => (
          <option key={choice} value={choice}>
            {CHOICE_LABEL[choice] ?? choice}
          </option>
        ))}
      </select>
    );
  } else if (spec.kind === "list") {
    control = (
      <textarea id={id} className="textarea" value={Array.isArray(value) ? value.join("\n") : ""} onChange={(event) => onChange(event.target.value.split("\n"))} />
    );
  } else {
    control = <input id={id} className="input" value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)} />;
  }
  return (
    <Field
      label={spec.label}
      htmlFor={id}
      hint={
        <>
          {hint}
          {spec.kind === "list" ? "Her satıra bir anahtar kelime" : ""}
          {overridden ? (
            <span className="ml-2">
              <Badge tone="info">Ekip değeri</Badge>{" "}
              <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
                Genele dön
              </button>
            </span>
          ) : null}
        </>
      }
    >
      {control}
    </Field>
  );
}

function TelegramCard({ tokenSet }: { tokenSet: boolean }) {
  const { engine, reload, toast } = useEngine();
  const admin = useAdmin();
  const [token, setToken] = useState("");
  const [chat, setChat] = useState("");
  const [error, setError] = useState<string | null>(null);

  const guard = async (reason: string, action: (pin: string) => Promise<void>, success: string) => {
    setError(null);
    try {
      const done = await admin.run(reason, async (pin) => {
        await action(pin);
        return true;
      });
      if (done) {
        toast("success", success);
        await reload();
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  };

  const saveToken = async (event: FormEvent) => {
    event.preventDefault();
    await guard("Telegram jetonunu kaydetmek için yönetici doğrulaması gerekir", (pin) => engine.setTelegramToken(pin, token), "Jeton Windows Kimlik Yöneticisi’ne kaydedildi");
    setToken("");
  };

  return (
    <Card kicker="Bildirim kanalı" title={<span className="flex items-center gap-2"><PlatformLogo platform="Telegram" size={20} /> Telegram botu</span>} actions={<Badge tone={tokenSet ? "success" : "warning"}>{tokenSet ? "Jeton kayıtlı" : "Jeton yok"}</Badge>}>
      <div className="flex flex-col gap-3">
        <div className="muted">
          BotFather’dan aldığınız jeton veritabanına veya dosyaya yazılmaz; işletim sisteminin kimlik deposunda tutulur ve arayüzde bir daha gösterilmez.
        </div>
        <form onSubmit={(event) => void saveToken(event)} className="flex items-end gap-2">
          <div className="flex-1">
            <Field label="Bot jetonu" htmlFor="tg-token">
              <input id="tg-token" className="input" type="password" autoComplete="off" placeholder="123456:ABC…" value={token} onChange={(event) => setToken(event.target.value)} />
            </Field>
          </div>
          <Button type="submit" variant="primary" disabled={token.trim() === ""}>
            Kaydet
          </Button>
          {tokenSet ? (
            <Button variant="danger" onClick={() => void guard("Jetonu silmek için yönetici doğrulaması gerekir", (pin) => engine.clearTelegramToken(pin), "Jeton silindi")}>
              Sil
            </Button>
          ) : null}
        </form>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Field label="Test mesajı için sohbet kimliği" htmlFor="tg-chat">
              <input id="tg-chat" className="input" inputMode="numeric" value={chat} onChange={(event) => setChat(event.target.value)} />
            </Field>
          </div>
          <Button disabled={!tokenSet || chat.trim() === ""} onClick={() => void guard("Test mesajı göndermek için yönetici doğrulaması gerekir", (pin) => engine.testTelegram(pin, chat.trim()), "Test mesajı gönderildi")}>
            Test gönder
          </Button>
        </div>
        {error ? <Alert tone="danger">{error}</Alert> : null}
      </div>
    </Card>
  );
}

function ChannelSecretsCard({ secrets }: { secrets: Record<string, boolean> }) {
  const { engine, reload, toast } = useEngine();
  const admin = useAdmin();
  const [password, setPassword] = useState("");
  const [webhook, setWebhook] = useState("");
  const [to, setTo] = useState("");
  const [error, setError] = useState<string | null>(null);

  const guard = async (reason: string, action: (pin: string) => Promise<unknown>, success: string) => {
    setError(null);
    try {
      const done = await admin.run(reason, async (pin) => {
        await action(pin);
        return true;
      });
      if (done) {
        toast("success", success);
        await reload();
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  };

  const secretRow = (name: string, label: string, value: string, setValue: (v: string) => void, placeholder: string) => (
    <form
      className="flex items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        void guard(`${label} kaydetmek için yönetici doğrulaması gerekir`, (pin) => engine.setSecret(pin, name, value), `${label} kimlik deposuna kaydedildi`).then(() => setValue(""));
      }}
    >
      <div className="flex-1">
        <Field label={label} htmlFor={`secret-${name}`} hint={secrets[name] ? "Kayıtlı — değiştirmek için yenisini yazın" : "Kayıtlı değil"}>
          <input id={`secret-${name}`} className="input" type="password" autoComplete="off" placeholder={placeholder} value={value} onChange={(event) => setValue(event.target.value)} />
        </Field>
      </div>
      <Button type="submit" variant="primary" disabled={value.trim() === ""}>
        Kaydet
      </Button>
      {secrets[name] ? (
        <Button variant="danger" onClick={() => void guard(`${label} silmek için yönetici doğrulaması gerekir`, (pin) => engine.clearSecret(pin, name), `${label} silindi`)}>
          Sil
        </Button>
      ) : null}
    </form>
  );

  return (
    <Card kicker="Bildirim kanalı" title="E-posta ve Teams sırları" actions={<Badge tone="info">Kimlik deposu</Badge>}>
      <div className="flex flex-col gap-3">
        <div className="muted">Sırlar veritabanına, günlüklere veya dışa aktarmaya yazılmaz; arayüzde bir daha gösterilmez.</div>
        {secretRow("smtp_password", "SMTP parolası", password, setPassword, "Uygulama parolası")}
        {secretRow("teams_webhook", "Teams gelen webhook adresi", webhook, setWebhook, "https://…webhook.office.com/…")}
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1">
            <Field label="Test e-postası alıcısı" htmlFor="test-email">
              <input id="test-email" className="input" type="email" value={to} onChange={(event) => setTo(event.target.value)} />
            </Field>
          </div>
          <Button disabled={to.trim() === ""} onClick={() => void guard("Test e-postası için yönetici doğrulaması gerekir", (pin) => engine.testEmail(pin, to.trim()), "Test e-postası gönderildi")}>
            Test e-postası
          </Button>
          <Button disabled={!secrets.teams_webhook} onClick={() => void guard("Teams testi için yönetici doğrulaması gerekir", (pin) => engine.testTeams(pin), "Teams test mesajı gönderildi")}>
            Teams testi
          </Button>
        </div>
        {error ? <Alert tone="danger">{error}</Alert> : null}
      </div>
    </Card>
  );
}

const LOGIN_PLATFORMS = ["X", "Instagram", "Facebook", "Threads"] as const;

function SessionsCard() {
  const { engine, toast } = useEngine();
  const admin = useAdmin();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const login = async (platform: string) => {
    setError(null);
    setBusy(platform);
    try {
      const done = await admin.run(`${platform} oturumu açmak için yönetici doğrulaması gerekir`, (pin) => engine.loginSession(pin, platform));
      if (done !== null) toast("success", `${platform} oturumu kaydedildi (pencereyi kapattığınızda geçerlidir)`);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card kicker="Bağlantılar" icon="connections" title="Tarayıcı oturumları">
      <div className="flex flex-col gap-3">
        <Alert tone="info" title="Yalnızca sizin kendi oturumunuz kullanılır">
          “Oturum aç” gerçek bir Edge/Chrome penceresi açar; hesabınıza kendiniz girersiniz. Uygulama CAPTCHA çözmez, bot korumasını aşmaya veya
          parmak izi taklidine çalışmaz; bot koruması görülürse ilgili platformu bir süre dinlendirir ve o linkleri elle girmenizi bekler.
        </Alert>
        <div className="flex flex-wrap gap-2">
          {LOGIN_PLATFORMS.map((platform) => (
            <Button key={platform} busy={busy === platform} onClick={() => void login(platform)}>
              {busy === platform ? null : <PlatformLogo platform={platform} size={16} />}
              {platform} oturumu aç
            </Button>
          ))}
        </div>
        {busy ? <div className="muted">Pencere açıldı: giriş yaptıktan sonra pencereyi kapatın.</div> : null}
        {error ? <Alert tone="danger">{error}</Alert> : null}
      </div>
    </Card>
  );
}

function OperationsCard() {
  const { engine, reload, toast } = useEngine();
  const admin = useAdmin();
  const [testClock, setTestClock] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (label: string, action: (pin: string) => Promise<string>) => {
    setError(null);
    setBusy(label);
    try {
      const message = await admin.run(`${label} için yönetici doğrulaması gerekir`, action);
      if (message !== null) {
        toast("success", message);
        await reload();
      }
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card kicker="Test saati" icon="chart" title="Elle tetikleme ve test">
      <div className="flex flex-col gap-3">
        <div className="muted">
          Gece 00:00 kontrolü otomatik çalışır. Burada kuralları test saatiyle deneyebilirsiniz (gerçek uyarı üretir; bildirimler kapalıysa mesaj gitmez).
        </div>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Field label="Test saati (opsiyonel)" htmlFor="test-clock" hint="Boşsa şimdiki zaman kullanılır.">
              <input id="test-clock" className="input" type="datetime-local" value={testClock} onChange={(event) => setTestClock(event.target.value)} />
            </Field>
          </div>
          <Button
            variant="warning"
            busy={busy === "Hareketsizlik kontrolü"}
            onClick={() =>
              void run("Hareketsizlik kontrolü", async (pin) => {
                const result = await engine.strikeCheck(pin, testClock ? new Date(testClock).toISOString() : undefined);
                return result.strikes.length === 0
                  ? "Uyarı gerektiren kullanıcı yok"
                  : result.strikes.map((s) => `${s.user}: uyarı ${s.number}${s.flagged ? " (İŞARETLENDİ)" : ""}`).join(" · ");
              })
            }
          >
            Kontrolü şimdi çalıştır
          </Button>
        </div>
        <div>
          <Button
            busy={busy === "Bildirim gönderimi"}
            onClick={() =>
              void run("Bildirim gönderimi", async (pin) => {
                const result = await engine.flush(pin);
                if (result.held) return "Bildirimler kapalı; gönderim yapılmadı";
                return `Gönderilen ${result.sent} · yeniden denenecek ${result.retrying} · başarısız ${result.failed} · atlanan ${result.suppressed}`;
              })
            }
          >
            Bekleyen bildirimleri şimdi gönder
          </Button>
        </div>
        {error ? <Alert tone="danger">{error}</Alert> : null}
      </div>
    </Card>
  );
}

function PinCard({ pinSet }: { pinSet: boolean }) {
  const { engine, reload, toast } = useEngine();
  const admin = useAdmin();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await engine.setPin(next, pinSet ? current : null);
      admin.lock();
      setCurrent("");
      setNext("");
      toast("success", "PIN güncellendi");
      await reload();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  };

  return (
    <Card kicker="Güvenlik" icon="profile" title="Yönetici PIN’i" actions={<Badge tone={pinSet ? "success" : "warning"}>{pinSet ? "Belirlendi" : "Belirlenmedi"}</Badge>}>
      <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-3">
        <div className="muted">Ayar, ekip ve kullanıcı yönetimi PIN ister. Bu yerel bir kapıdır; disk erişimi olan birine karşı güvenlik sınırı değildir.</div>
        <div className="grid grid-cols-2 gap-3">
          {pinSet ? (
            <Field label="Mevcut PIN" htmlFor="pin-current">
              <input id="pin-current" className="input" type="password" autoComplete="off" value={current} onChange={(event) => setCurrent(event.target.value)} />
            </Field>
          ) : null}
          <Field label="Yeni PIN (en az 6 karakter)" htmlFor="pin-new">
            <input id="pin-new" className="input" type="password" autoComplete="off" value={next} onChange={(event) => setNext(event.target.value)} />
          </Field>
        </div>
        {error ? <Alert tone="danger">{error}</Alert> : null}
        <div>
          <Button type="submit" variant="primary" disabled={next.length < 6}>
            {pinSet ? "PIN’i değiştir" : "PIN belirle"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function About() {
  return (
    <div className="muted pb-4 text-center text-[11px]">
      Etkileşim Takip v0.1.0 · created by axthrowa
    </div>
  );
}
