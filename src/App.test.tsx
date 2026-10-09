import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { App } from "./App";
import { createEngine } from "./lib/engine";
import { PREVIEW_PIN, createMockTransport } from "./lib/mock";
import { AdminProvider } from "./state/AdminContext";
import { EngineProvider } from "./state/EngineContext";

function renderApp() {
  const engine = createEngine(createMockTransport(), true);
  return render(
    <EngineProvider engine={engine}>
      <AdminProvider>
        <App />
      </AdminProvider>
    </EngineProvider>,
  );
}

type User = ReturnType<typeof userEvent.setup>;

async function switchToAdmin(user: User, pin = PREVIEW_PIN) {
  await user.click(await screen.findByRole("button", { name: /Yönetici hesabına geç/ }));
  const dialog = await screen.findByRole("form", { name: "Yönetici girişi" });
  await user.type(within(dialog).getByLabelText("PIN"), pin);
  await user.click(within(dialog).getByRole("button", { name: "Doğrula" }));
  return dialog;
}

async function openShares(user: User) {
  await user.click(await screen.findByRole("button", { name: /Paylaşımlar/ }));
}

beforeEach(() => window.localStorage.clear());
afterEach(cleanup);

describe("accounts", () => {
  it("opens in the first user account with admin tabs hidden", async () => {
    renderApp();
    expect(await screen.findByText(/DEMO — örnek veriler/)).toBeInTheDocument();
    expect(await screen.findByText(/Kullanıcı hesabı/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Hesap")).toHaveDisplayValue("Ayşe Demir"));
    expect(screen.queryByRole("button", { name: /Ekip yönetimi/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Bağlantılar & ayarlar/ })).toBeNull();
  });

  it("shows only the account's own posts and switches with the account", async () => {
    const user = userEvent.setup();
    renderApp();
    await openShares(user);
    await waitFor(() => expect(screen.getByLabelText("Paylaşan kişi")).toHaveValue("Ayşe Demir"));
    const table = (await screen.findAllByRole("table"))[0] as HTMLElement;
    expect(within(table).queryByText("Burak Yıldız")).toBeNull();
    expect(within(table).getAllByText("Ayşe Demir").length).toBeGreaterThan(0);
    await user.selectOptions(screen.getByLabelText("Hesap"), "Cem Kaya");
    await waitFor(() => expect(screen.getByLabelText("Paylaşan kişi")).toHaveValue("Cem Kaya"));
    await waitFor(() => expect(within(screen.getAllByRole("table")[0] as HTMLElement).queryByText("Ayşe Demir")).toBeNull());
  });

  it("asks for the PIN to switch to the admin account and rejects a wrong PIN", async () => {
    const user = userEvent.setup();
    renderApp();
    const dialog = await switchToAdmin(user, "000000");
    expect(await within(dialog).findByText(/PIN'i hatalı/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Ekip yönetimi/ })).toBeNull();
  });

  it("switches to the admin account after the correct PIN and back again", async () => {
    const user = userEvent.setup();
    renderApp();
    await switchToAdmin(user);
    expect(await screen.findByText("Yönetici hesabı")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ekip yönetimi/ })).toBeInTheDocument();
    expect(await screen.findByText(/yönetici incelemesi bekliyor/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Kullanıcı hesabına dön/ }));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Ekip yönetimi/ })).toBeNull());
  });
});

describe("shares", () => {
  it("never shows unknown metrics as zero and uses platform logos", async () => {
    const user = userEvent.setup();
    renderApp();
    await openShares(user);
    const table = (await screen.findAllByRole("table"))[0] as HTMLElement;
    const instagram = (await within(table).findByRole("img", { name: "Instagram" })).closest("tr");
    expect(instagram).not.toBeNull();
    const cells = within(instagram as HTMLElement).getAllByRole("cell");
    // Beğeni, Yorum, Paylaşım, İzlenme sütunları ölçülmedi → "—"
    expect(cells.slice(2, 6).map((c) => c.textContent)).toEqual(["—", "—", "—", "—"]);
    expect(within(instagram as HTMLElement).getByText("Giriş gerekli")).toBeInTheDocument();
  });

  it("recognises the platform while the link is typed", async () => {
    const user = userEvent.setup();
    renderApp();
    await openShares(user);
    await user.type(await screen.findByLabelText(/Paylaşım linki/), "https://www.reddit.com/r/x/comments/abc/");
    expect(await screen.findByText(/bağlantısı tanındı/)).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: "Reddit" }).length).toBeGreaterThan(0);
  });

  it("warns about recently used communities and shows the team's notes about the page", async () => {
    const user = userEvent.setup();
    renderApp();
    await openShares(user);
    await user.type(await screen.findByLabelText(/Paylaşılan topluluk/), "r/IndieGaming");
    expect((await screen.findAllByText("Yakın zamanda kullanıldı", undefined, { timeout: 3000 })).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Mehmet Aksoy/).length).toBeGreaterThan(0);
    expect(screen.getByText("Ekibin bu sayfa hakkındaki notları")).toBeInTheDocument();
    expect(screen.getAllByText(/Moderatörler doğrudan Steam linkini siliyor/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Yine de kaydet" })).toBeInTheDocument();
  });

  it("saves the poster's page note with the link", async () => {
    const user = userEvent.setup();
    renderApp();
    await openShares(user);
    await waitFor(() => expect(screen.getByLabelText("Paylaşan kişi")).toHaveValue("Ayşe Demir"));
    await user.type(await screen.findByLabelText(/Paylaşım linki/), "https://x.com/ayse/status/77");
    await user.type(screen.getByLabelText("Sayfa hakkında not"), "Cuma akşamları çok aktif");
    await user.click(screen.getByRole("button", { name: "Takibi başlat" }));
    expect(await screen.findByText(/Not: Cuma akşamları çok aktif/)).toBeInTheDocument();
  });

  it("reports a clean community without warning", async () => {
    const user = userEvent.setup();
    renderApp();
    await openShares(user);
    await user.type(await screen.findByLabelText(/Paylaşılan topluluk/), "Yeni Topluluk");
    expect(await screen.findByText(/henüz paylaşım yapılmadı \(Temiz\)/, undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Takibi başlat" })).toBeInTheDocument();
  });

  it("surfaces engine validation errors", async () => {
    const user = userEvent.setup();
    renderApp();
    await openShares(user);
    await user.type(await screen.findByLabelText(/Paylaşım linki/), "http://localhost/admin");
    await user.click(screen.getByRole("button", { name: "Takibi başlat" }));
    expect(await screen.findByText(/Yerel ağ adresleri kabul edilmez/)).toBeInTheDocument();
  });
});

describe("admin settings", () => {
  async function openSettings() {
    const user = userEvent.setup();
    renderApp();
    await switchToAdmin(user);
    await user.click(await screen.findByRole("button", { name: /Bağlantılar & ayarlar/ }));
    await screen.findByText("Hatırlatma ve uyarı (strike) kuralları");
    return user;
  }

  it("saves rules without asking for the PIN again", async () => {
    const user = await openSettings();
    const days = screen.getByLabelText("Hareketsizlik eşiği (gün)");
    await user.clear(days);
    await user.type(days, "5");
    await user.click(screen.getByRole("button", { name: "Ayarları kaydet" }));
    expect(await screen.findByText(/Ayarlar kaydedildi/)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Yönetici girişi" })).toBeNull();
    await waitFor(() => expect(screen.getByLabelText("Hareketsizlik eşiği (gün)")).toHaveValue(5));
  });

  it("shows only team-overridable rules in team scope", async () => {
    const user = await openSettings();
    await user.selectOptions(screen.getByLabelText("Ayar kapsamı"), "1");
    await screen.findByText(/Ekip bazında yalnızca uyarı kuralları/);
    expect(screen.getByLabelText("Hareketsizlik eşiği (gün)")).toBeInTheDocument();
    expect(screen.queryByLabelText("Ölçüm aralığı (saat)")).toBeNull();
  });

  it("rejects an empty number field", async () => {
    const user = await openSettings();
    await user.clear(screen.getByLabelText("Hareketsizlik eşiği (gün)"));
    await user.click(screen.getByRole("button", { name: "Ayarları kaydet" }));
    expect(await screen.findByText(/arasında bir tam sayı girin/)).toBeInTheDocument();
  });
});

describe("team screen", () => {
  it("shows strike dots, flagged status and the notification queue", async () => {
    const user = userEvent.setup();
    renderApp();
    await switchToAdmin(user);
    await user.click(await screen.findByRole("button", { name: /Ekip yönetimi/ }));
    expect(await screen.findByText("İNCELEME GEREKLİ")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "3/3 uyarı" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Bildirimler/ }));
    expect(await screen.findByText(/Gönderim kuyruğu/)).toBeInTheDocument();
    expect(screen.getByText("Hedef yok", { selector: "span" })).toBeInTheDocument();
    expect(await screen.findByText("Burak Yıldız yönetici incelemesi bekliyor")).toBeInTheDocument();
  });
});

describe("master prompt features", () => {
  it("shows a team manager the whole team in the user account", async () => {
    const user = userEvent.setup();
    renderApp();
    const account = await screen.findByRole("combobox", { name: "Hesap" });
    await within(account).findByRole("option", { name: "Deniz Acar" });
    await user.selectOptions(account, "Deniz Acar");
    expect(await screen.findByText(/Ekip yöneticisi/)).toBeInTheDocument();
    await openShares(user);
    const table = await screen.findByRole("table");
    expect((await within(table).findAllByText("Cem Kaya")).length).toBeGreaterThan(0);
    expect(within(table).queryByText("Ayşe Demir")).not.toBeInTheDocument();
  });

  it("shows the analytics leaderboard and filters by campaign", async () => {
    const user = userEvent.setup();
    renderApp();
    await user.click(await screen.findByRole("button", { name: /Analitik/ }));
    expect(await screen.findByText("Performans puanı")).toBeInTheDocument();
    expect(await screen.findByText("Çıkış / erişim sorusu")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Kampanya"), "Skyforge Kickstarter");
    expect(await screen.findByText("Skyforge Tales")).toBeInTheDocument();
  });

  it("lets a user read and clear their own inbox", async () => {
    const user = userEvent.setup();
    renderApp();
    const account = await screen.findByRole("combobox", { name: "Hesap" });
    await within(account).findByRole("option", { name: "Cem Kaya" });
    await user.selectOptions(account, "Cem Kaya");
    await user.click(screen.getByRole("button", { name: /Bildirimler/ }));
    expect(await screen.findByText("Paylaşım hatırlatması 1/3")).toBeInTheDocument();
    expect(screen.queryByText(/Gönderim kuyruğu/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tümünü okundu say" }));
    expect(await screen.findByText("Tüm bildirimler okundu")).toBeInTheDocument();
  });

  it("explains community recommendations with reasons", async () => {
    const user = userEvent.setup();
    renderApp();
    await user.click(await screen.findByRole("button", { name: /Topluluk keşfi/ }));
    expect((await screen.findAllByText(/Daha önce hiç paylaşım yapılmamış/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Öneri puanı").length).toBeGreaterThan(0);
  });

  it("searches posts globally and opens the post", async () => {
    const user = userEvent.setup();
    renderApp();
    await switchToAdmin(user);
    await user.type(screen.getByRole("searchbox", { name: "Ara" }), "IndieGaming");
    const list = await screen.findByRole("listbox", { name: "Arama sonuçları" });
    const option = (await within(list).findAllByRole("option"))[0];
    if (!option) throw new Error("arama sonucu yok");
    await user.click(option);
    expect(await screen.findByRole("dialog", { name: "Gönderi ayrıntısı" })).toBeInTheDocument();
  });

  it("gives the admin campaign and system screens", async () => {
    const user = userEvent.setup();
    renderApp();
    await switchToAdmin(user);
    await user.click(await screen.findByRole("button", { name: /Kampanyalar/ }));
    expect(await screen.findByText("Nova Beta Duyurusu")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Sistem/ }));
    expect(await screen.findByText("Platform sağlığı")).toBeInTheDocument();
    expect(await screen.findByText("Duraklatıldı")).toBeInTheDocument();
  });

  it("tags a new share with a campaign and content type", async () => {
    const user = userEvent.setup();
    renderApp();
    await openShares(user);
    expect(screen.getByLabelText("Kampanya")).toBeInTheDocument();
    expect(screen.getByLabelText("İçerik türü")).toBeInTheDocument();
  });
});
