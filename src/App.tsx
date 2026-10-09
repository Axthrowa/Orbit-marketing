import { useEffect, useState } from "react";

import { AddLinkForm } from "./components/AddLinkForm";
import type { Prefill } from "./components/AddLinkForm";
import { AnalyticsScreen } from "./components/AnalyticsScreen";
import { AudienceScreen } from "./components/AudienceScreen";
import { CampaignsScreen } from "./components/CampaignsScreen";
import { CommunityRadar } from "./components/CommunityRadar";
import { Dashboard } from "./components/Dashboard";
import { GlobalSearch } from "./components/GlobalSearch";
import type { SearchTarget } from "./components/GlobalSearch";
import { NotificationCenter } from "./components/NotificationCenter";
import { OrbitIcon } from "./components/OrbitIcon";
import type { OrbitIconName } from "./components/OrbitIcon";
import { SettingsScreen } from "./components/SettingsScreen";
import { SystemScreen } from "./components/SystemScreen";
import { TeamPerformance } from "./components/TeamPerformance";
import { Avatar, Button } from "./components/ui";
import { errorMessage } from "./lib/format";
import { useAdmin } from "./state/AdminContext";
import { useEngine } from "./state/EngineContext";

export type Tab =
  | "overview"
  | "shares"
  | "analytics"
  | "audience"
  | "communities"
  | "campaigns"
  | "team"
  | "system"
  | "settings"
  | "notifications";
type ThemePreference = "system" | "light" | "dark";

const NAV: { tab: Tab; label: string; icon: OrbitIconName; adminOnly?: boolean }[] = [
  { tab: "overview", label: "Genel bakış", icon: "overview" },
  { tab: "shares", label: "Paylaşımlar", icon: "shares" },
  { tab: "analytics", label: "Analitik", icon: "chart" },
  { tab: "audience", label: "Oyuncunun sesi", icon: "audience" },
  { tab: "communities", label: "Topluluk keşfi", icon: "communities" },
  { tab: "campaigns", label: "Kampanyalar", icon: "campaigns", adminOnly: true },
  { tab: "team", label: "Ekip yönetimi", icon: "management", adminOnly: true },
  { tab: "system", label: "Sistem", icon: "system", adminOnly: true },
  { tab: "settings", label: "Bağlantılar & ayarlar", icon: "connections", adminOnly: true },
];

const HEADINGS: Record<Tab, { kicker: string; title: string; subtitle: string }> = {
  overview: {
    kicker: "Pazarlamanın büyük resmi",
    title: "Büyük resim, sade bir bakış.",
    subtitle: "Ekibin ritmi ve her paylaşımın etkisi, bir arada.",
  },
  shares: {
    kicker: "Paylaşımlar",
    title: "Her linkin etkisi.",
    subtitle: "Linki ekle; etkileşim, yorumlar ve topluluk geçmişi kendiliğinden izlensin.",
  },
  analytics: {
    kicker: "Ölç, karşılaştır, öğren",
    title: "Neyin işe yaradığını gör.",
    subtitle: "Dönem, kampanya, oyun ve platforma göre etkileşim; ağırlıklı performans sıralaması.",
  },
  campaigns: {
    kicker: "Kampanyalar & oyunlar",
    title: "Her paylaşım bir hikâyenin parçası.",
    subtitle: "Oyunları ve kampanyaları tanımla; paylaşımlar ve öneriler bunlara göre şekillensin.",
  },
  system: {
    kicker: "Sistem",
    title: "Perde arkası.",
    subtitle: "Zamanlanmış işler, platform sağlığı, denetim günlüğü, dışa aktarma ve yedek.",
  },
  audience: {
    kicker: "Sayıların ötesinde",
    title: "Oyuncular ne hissediyor?",
    subtitle: "Yorumlar yerelde, Türkçe ve İngilizce olarak sınıflandırılır.",
  },
  communities: {
    kicker: "Doğru topluluklar",
    title: "Doğru yerde, doğru zamanda.",
    subtitle: "Keşfedilen topluluklar ve her birinde daha önce yapılan paylaşımlar.",
  },
  team: {
    kicker: "Emeğin görünür olsun",
    title: "Ekibin ritmi ve uyarılar.",
    subtitle: "Ekipler, kişiler, uyarı durumları ve hesaplar.",
  },
  settings: {
    kicker: "Bağlantılar & ayarlar",
    title: "Kurallar senin elinde.",
    subtitle: "Hatırlatma kuralları, Telegram/e-posta/Teams, performans ağırlıkları, saklama ve güvenlik.",
  },
  notifications: {
    kicker: "Ekibin nabzı",
    title: "Bildirim merkezi.",
    subtitle: "Uyarılar, yönetici bildirimleri ve gönderim durumları.",
  },
};

const THEME_KEY = "orbit.theme";
const ACCOUNT_KEY = "orbit.account";

function loadAccount(): number | null {
  try {
    const stored = Number(window.localStorage.getItem(ACCOUNT_KEY));
    return Number.isInteger(stored) && stored > 0 ? stored : null;
  } catch {
    return null; // depolama kısıtlı: ilk hesap seçilir
  }
}

function loadTheme(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    if (stored === "dark" || stored === "light" || stored === "system") return stored;
  } catch {
    // Depolama kısıtlı (ör. WebView): tema bellekte çalışır.
  }
  return "system";
}

function useTheme(): [ThemePreference, (value: ThemePreference) => void] {
  const [preference, setPreference] = useState<ThemePreference>(loadTheme);
  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    const apply = () => {
      const resolved = preference === "system" ? (media?.matches ? "dark" : "light") : preference;
      document.documentElement.dataset.theme = resolved;
    };
    apply();
    try {
      window.localStorage.setItem(THEME_KEY, preference);
    } catch {
      // Depolama yazılamıyor: tercih yalnızca bu oturumda geçerli.
    }
    media?.addEventListener?.("change", apply);
    return () => media?.removeEventListener?.("change", apply);
  }, [preference]);
  return [preference, setPreference];
}

export function App() {
  const { engine, state, reload, teamFilter, setTeamFilter, setViewerUserId, toast } = useEngine();
  const admin = useAdmin();
  const isAdmin = admin.unlocked;
  const [tab, setTab] = useState<Tab>("overview");
  const [accountId, setAccountId] = useState<number | null>(loadAccount);
  const accounts = state?.accounts ?? [];
  const account = accounts.find((a) => a.id === accountId) ?? null;

  // Uygulama kullanıcı hesabıyla açılır; geçerli bir hesap yoksa ilk hesap seçilir.
  useEffect(() => {
    if (accounts.length > 0 && !accounts.some((a) => a.id === accountId)) setAccountId(accounts[0]?.id ?? null);
  }, [accounts, accountId]);

  // Ekip yöneticisi (manager) kullanıcı hesabında kendi ekibinin tamamını görür; üye/izleyici yalnız kendini.
  const isManager = !isAdmin && account?.role === "manager";
  const managerTeam = isManager ? (account?.team_id ?? null) : null;
  useEffect(() => {
    setTeamFilter(isAdmin ? null : managerTeam);
  }, [isAdmin, managerTeam, setTeamFilter]);

  useEffect(() => {
    setViewerUserId(isAdmin || isManager ? null : (accountId ?? 0));
    try {
      if (accountId !== null) window.localStorage.setItem(ACCOUNT_KEY, String(accountId));
    } catch {
      // depolama yazılamıyor: hesap seçimi yalnızca bu oturumda geçerli
    }
  }, [isAdmin, isManager, accountId, setViewerUserId]);

  useEffect(() => {
    if (!isAdmin && NAV.some((n) => n.tab === tab && n.adminOnly)) setTab("overview");
  }, [isAdmin, tab]);

  const switchToAdmin = async () => {
    try {
      const done = await admin.run("Yönetici hesabına geçmek için yönetici PIN’ini girin", (pin) => engine.verifyPin(pin));
      if (done !== null) toast("success", "Yönetici hesabına geçildi");
    } catch (caught) {
      toast("danger", errorMessage(caught));
    }
  };

  const switchToUser = () => {
    admin.lock();
    toast("info", "Kullanıcı hesabına dönüldü");
  };
  const [prefill, setPrefill] = useState<Prefill>({});
  const [theme, setTheme] = useTheme();
  const [refreshing, setRefreshing] = useState(false);
  const [measuring, setMeasuring] = useState(false);

  const flagged = state?.kpis.users_flagged ?? 0;
  const summary = state?.notification_summary ?? {};
  const attention = (state?.inbox_unread ?? 0) + (isAdmin ? (summary.failed ?? 0) + (summary.no_target ?? 0) : 0);
  const viewerId = isAdmin ? null : accountId;
  const openSearchResult = (target: SearchTarget) => {
    if (target.kind === "post") {
      setPrefill((old) => ({ openPostId: target.id, nonce: (old.nonce ?? 0) + 1 }));
      setTab("shares");
    } else if (target.kind === "community") {
      setPrefill((old) => ({ communityName: target.name, nonce: (old.nonce ?? 0) + 1 }));
      setTab("communities");
    } else if (target.kind === "person") setTab(isAdmin ? "team" : "analytics");
    else setTab(isAdmin ? "campaigns" : "analytics");
  };
  const heading = HEADINGS[tab];

  const refreshAll = async () => {
    setRefreshing(true);
    try {
      await reload();
    } finally {
      setRefreshing(false);
    }
  };

  const measureNow = async () => {
    setMeasuring(true);
    try {
      const result = await engine.refresh();
      if (result.checked === 0) toast("info", "Ölçüm zamanı gelmiş paylaşım yok");
      else toast(result.ok > 0 ? "success" : "warning", `${result.checked} paylaşım denendi · ${result.ok} güncellendi`);
      await reload();
    } catch (caught) {
      toast("danger", errorMessage(caught));
    } finally {
      setMeasuring(false);
    }
  };

  return (
    <div className="min-h-full">
      {engine.isPreview ? (
        <div className="demo-strip" role="note">
          DEMO — örnek veriler, gerçek ölçüm yapılmaz · Yönetici ekranları için PIN: 123456
        </div>
      ) : null}
      <header className="workspace-header">
        <button className="brand border-0 bg-transparent p-0" onClick={() => setTab("overview")} aria-label="Genel bakışa dön">
          <span className="brand-mark">
            <OrbitIcon name="orbit" />
          </span>
          <span className="text-left">
            orbit<small>etkileşim takip</small>
          </span>
        </button>
        <div className="header-tools">
          <GlobalSearch userId={viewerId} onPick={openSearchResult} />
          <label className="theme-control">
            Tema
            <select aria-label="Görünüm teması" value={theme} onChange={(event) => setTheme(event.target.value as ThemePreference)}>
              <option value="system">Sistem</option>
              <option value="light">Açık</option>
              <option value="dark">Karanlık</option>
            </select>
          </label>
          <span className={engine.isPreview ? "mode-badge" : "mode-badge live"}>{engine.isPreview ? "Demo modu" : "Yerel motor"}</span>
          {state?.provider_mode === "mock" ? (
            <span className="mode-badge" title="ETKILESIM_PROVIDER_MODE=mock: sayılar gerçek platformlardan gelmiyor">
              MOCK DATA
            </span>
          ) : null}
          <button className="notification-button" onClick={() => setTab("notifications")}>
            <OrbitIcon name="bell" />
            Bildirimler <span className={attention > 0 ? "count alarm" : "count"}>{attention}</span>
          </button>
          {isAdmin ? (
          <label className="theme-control">
            Ekip
            <select aria-label="Ekip filtresi" value={teamFilter === null ? "" : String(teamFilter)} onChange={(event) => setTeamFilter(event.target.value === "" ? null : Number(event.target.value))}>
              <option value="">Tüm ekipler</option>
              {(state?.teams ?? []).map((team) => (
                <option key={team.id} value={team.id}>
                  {team.name}
                </option>
              ))}
            </select>
          </label>
          ) : null}
          {isAdmin ? (
            <div className="identity">
              <span className="avatar">
                <OrbitIcon name="management" />
              </span>
              <span>
                <strong>Yönetici hesabı</strong>
                <small>Tüm ekipler, kurallar ve ayarlar</small>
              </span>
              <Button small icon="profile" onClick={switchToUser}>
                Kullanıcı hesabına dön
              </Button>
            </div>
          ) : (
            <div className="identity">
              {account ? <Avatar name={account.name} /> : <span className="avatar" />}
              <span>
                <strong>{account?.name ?? "Hesap yok"}</strong>
                <small>
                  {isManager ? "Ekip yöneticisi" : account?.role === "viewer" ? "İzleyici (salt okunur)" : "Kullanıcı hesabı"}
                  {account?.team_name ? ` · ${account.team_name}` : ""}
                </small>
              </span>
              <label className="account-switch">
                <span className="sr-only">Hesap</span>
                <select aria-label="Hesap" value={accountId ?? ""} onChange={(event) => setAccountId(Number(event.target.value))}>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </label>
              <Button small variant="primary" icon="management" onClick={() => void switchToAdmin()}>
                Yönetici hesabına geç
              </Button>
            </div>
          )}
        </div>
      </header>
      <nav className="workspace-nav" aria-label="Çalışma alanı">
        {NAV.filter((item) => isAdmin || !item.adminOnly).map((item) => (
          <button key={item.tab} className="nav-link" aria-current={tab === item.tab ? "page" : undefined} onClick={() => setTab(item.tab)}>
            <OrbitIcon name={item.icon} />
            {item.label}
            {item.tab === "team" && flagged > 0 ? <span className="pill-count">{flagged}</span> : null}
          </button>
        ))}
        <span className="nav-tail">Küçük adımlar. Ölçülebilir etki.</span>
      </nav>

      <main className="workspace-main">
        <div className="page-heading">
          <div>
            <p className="kicker">{heading.kicker}</p>
            <h1>{heading.title}</h1>
            <p className="muted">{heading.subtitle}</p>
          </div>
          <div className="top-actions">
            <Button icon="refresh" busy={refreshing} onClick={() => void refreshAll()}>
              Yenile
            </Button>
            {tab === "overview" || tab === "shares" ? (
              <Button variant="primary" icon="chart" busy={measuring} onClick={() => void measureNow()}>
                Ölçümü çalıştır
              </Button>
            ) : null}
          </div>
        </div>

        {tab === "overview" ? <Dashboard onNavigate={setTab} /> : null}
        {tab === "shares" ? (
          <AddLinkForm prefill={prefill} accountId={isAdmin ? null : accountId} onFindCommunity={() => setTab("communities")} />
        ) : null}
        {tab === "analytics" ? (
          <AnalyticsScreen userId={isManager ? null : viewerId} teamId={isAdmin ? teamFilter : managerTeam} />
        ) : null}
        {tab === "audience" ? <AudienceScreen userId={isManager ? null : viewerId} teamId={isAdmin ? teamFilter : managerTeam} /> : null}
        {tab === "campaigns" ? <CampaignsScreen /> : null}
        {tab === "system" ? <SystemScreen /> : null}
        {tab === "communities" ? (
          <CommunityRadar
            isAdmin={isAdmin}
            onUse={(communityName) => {
              setPrefill({ communityName });
              setTab("shares");
            }}
          />
        ) : null}
        {tab === "team" ? <TeamPerformance /> : null}
        {tab === "settings" ? <SettingsScreen /> : null}
        {tab === "notifications" ? <NotificationCenter isAdmin={isAdmin} userId={accountId} /> : null}

        <footer className="app-footer">
          orbit · daha görünür bir emek, daha anlamlı bir etki.
          <span>created by axthrowa · Yerel çalışma alanı · otomatik işler için uygulama açık kalmalı</span>
        </footer>
      </main>
    </div>
  );
}
