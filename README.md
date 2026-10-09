# Etkileşim Takip

Gerilla pazarlama takip, istatistik, duygu analizi ve topluluk keşif platformu (Windows masaüstü).
**created by axthrowa**

- Ekip üyelerinin paylaştığı linkleri kaydeder, etkileşimlerini periyodik ölçer (zaman serisi).
- Yorumları yerelde Türkçe/İngilizce duygu analizinden geçirir (% olumlu / % olumsuz).
- Aynı topluluğa daha önce paylaşım yapıldıysa tarih, paylaşan kişi ve 150 karakterlik önizlemeyi gösterir.
- Anahtar kelimelerle açık oyuncu topluluklarını keşfeder ve önerir (otomatik paylaşım yapmaz).
- Paylaşım yapmayan kullanıcıları yönetici ayarlı kurallarla Telegram'dan uyarır; son uyarıda
  kullanıcıyı işaretler ve yöneticiye bildirir.
- Çok ekipli: kurallar genel veya ekip bazında ayarlanır.

Harici ücretli API kullanılmaz.

## Mimari

```
React 18 + TypeScript + Tailwind (src/)
        │ Tauri invoke (beyaz listeli komutlar)
Tauri v2 / Rust kabuğu (src-tauri/)
        │ alt süreç: komut + stdin JSON (PIN yalnızca ortam değişkeninde)
Python motoru (engine/etkilesim)  ── SQLite (WAL) %LOCALAPPDATA%\EtkilesimTakip\etkilesim.db
        └─ daemon (APScheduler): ölçüm turları · 00:00 hareketsizlik kontrolü · keşif · Telegram kuyruğu
```

Ayrıntılı kararlar: [`docs/00-analiz-ve-ADR.md`](docs/00-analiz-ve-ADR.md). Geliştirici kuralları: [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Gereksinimler

- Windows 10/11, Microsoft Edge veya Google Chrome (tarayıcı ölçümü için; ayrıca indirme yapılmaz)
- Python 3.11+ · Node.js 20+ · Rust (stable) + Tauri v2 önkoşulları (WebView2)

## Geliştirme kurulumu

```powershell
cd engine
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[browser,dev]"
cd ..
npm install
npm run app:dev
```

`npm run app:dev` Vite'ı (port 1420) ve Tauri penceresini açar; motor `engine\.venv` üzerinden
çalışır, zamanlayıcı (daemon) uygulamayla birlikte başlar ve kapanır.

Yalnızca arayüzü tarayıcıda görmek için `npm run dev`: gerçek motor yoktur, ekranın üstünde
**DEMO** şeridi görünür (önizleme yönetici PIN'i `123456`). Bu demo motoru üretim paketine girmez.

Müşteriye gösterilecek demolar (örnek verilerle, DEMO şeridiyle; gerçek motor/ölçüm yok):

- Tek HTML: `node scripts/build-demo.mjs <çıktı.html>`
- Taşınabilir exe (kurulumsuz, WebView2 gerekir): `npx tauri build --no-bundle --config src-tauri/tauri.demo.conf.json`
  → `src-tauri/target/release/etkilesim-takip.exe`

## Hesaplar

Uygulama **kullanıcı hesabıyla** açılır: kişi yalnızca kendi paylaşımlarını, sayaçlarını ve bildirimlerini
görür; paylaşan kişi hesaptan alınır. **Ekip yöneticisi** (manager) rolündeki hesap kendi ekibinin tüm
paylaşımlarını ve analitiğini görür; **İzleyici** (viewer) salt okunurdur, link ekleyemez. **Yönetici hesabına geç** yönetici PIN'ini ister; doğrulanınca
tüm ekipler, Ekip yönetimi ve Bağlantılar & ayarlar açılır. **Kullanıcı hesabına dön** PIN'i bellekten siler.
Bu yerel bir görünüm ayrımıdır; çok makineli gerçek hesap sistemi değildir.

## Oyunlar, kampanyalar ve analitik

- **Kampanyalar** (yönetici): oyun (tür, dil, anahtar kelime) ve kampanya (tarih, durum) tanımlanır. Link
  eklerken kampanya ve içerik türü (gönderi/video/görsel/anket/etkinlik) seçilir; oyun kampanyadan gelir.
- **Analitik**: dönem (24 sa/7/30/90/365 gün/tümü), kampanya, oyun ve platform filtreleri; platform, içerik
  türü, kampanya, oyun ve topluluk kırılımları; yorum konuları (çıkış sorusu, bug, fiyat, performans…).
- **Lider tablosu**: düzenli paylaşım, etkileşim, oyuncu tepkisi, topluluk çeşitliliği, etkileşim hızı ve
  kampanya katkısından ağırlıklı **performans puanı**. Ağırlıklar Ayarlar → *Performans puanı ağırlıkları*.
- **Topluluk önerileri**: oyun/kampanya seçilerek konu uyumu, etkinlik, geçmiş etkileşim, tazelik, dil ve
  kitle uyumundan puanlanır; spam riski ve yakın kullanım puanı düşürür. Her kartta artı/eksi gerekçeler yazar.
- **Genel arama** (üst başlık): link, not, kişi, topluluk, kampanya ve oyun.
- Gönderi ayrıntısı: ilk 1/6/24 saatteki etkileşim hızı, artış, etkileşim oranı; yönetici gönderiyi
  **arşivleyebilir** (silinmez, ölçüm geçmişi kalır).

## Bildirim kanalları

Uyarılar ve özetler **uygulama içi gelen kutusuna** her zaman düşer (üstteki *Bildirimler* rozeti okunmamış
sayısını gösterir). Ek olarak açılan her kanala ayrı ayrı gönderilir:

| Kanal | Kurulum (Bağlantılar & ayarlar) |
|---|---|
| Telegram | BotFather jetonu → *Telegram botu*; kişilerin sayısal Telegram kimliği |
| E-posta | *E-posta ve Microsoft Teams* grubunda SMTP sunucusu, portu (465 SSL, 587 STARTTLS), kullanıcı, gönderen ve yönetici adresi; parola *E-posta ve Teams sırları* kartından (kimlik deposu). Gmail için uygulama parolası gerekir. Kişilerin e-posta adresi Ekip yönetiminden girilir. |
| Microsoft Teams | Teams kanalında *Workflows → Post to a channel when a webhook request is received* (veya Gelen Webhook) ile adres oluşturun, *Teams gelen webhook adresi* olarak kaydedin, *Teams testi* ile deneyin, sonra *Microsoft Teams bildirimleri açık* ayarını açın. Mesaj Adaptive Card olarak gider. |

Kapalı kanala hiçbir şey gitmez; açıldığında önceden birikenler toplu gönderilmez.

## Sistem ekranı, yedekleme ve saklama

Yönetici **Sistem** sekmesinde: zamanlanmış işlerin son durumu ve **Şimdi çalıştır**, iş geçmişi, platform
sağlığı (7 günlük başarı oranı, kuyruk, devre durumu *Çalışıyor / Deneniyor / Duraklatıldı*), **başarısızları
yeniden dene**, uyarı geçmişi ve denetim günlüğü bulunur.

- **Dışa aktarma**: XLSX (her veri kümesi bir sayfa), CSV (paylaşımlar; `;` ayırıcı, BOM'lu UTF-8) veya JSON
  → *İndirilenler*. Hücreler formül enjeksiyonuna karşı temizlenir.
- **Yedek**: her gece ve istenince `%LOCALAPPDATA%\EtkilesimTakip\backups\etkilesim-YYYYMMDD-HHMMSS.db`
  (SQLite çevrimiçi yedek API'si; uygulama açıkken güvenli). En yeni *Tutulacak günlük yedek sayısı* kadarı
  saklanır. **Geri yükleme**: uygulamayı kapatın, `etkilesim.db` dosyasını yedekle değiştirin
  (`-wal`/`-shm` dosyalarını silin), uygulamayı açın.
- **Saklama**: yorum metinleri *Yorum metni saklama süresi* (varsayılan 180 gün), denetim kayıtları *Denetim
  günlüğü saklama süresi* (365 gün) sonra her gece temizlenir; sayılar ve uyarı geçmişi kalır. 0 = süresiz.

## Veritabanı geçişleri (migrations)

Şema sürümü `PRAGMA user_version` ile tutulur. `engine/etkilesim/schema.sql` v1 tabanıdır;
`engine/etkilesim/migrations.py` sürüm adımlarını sırayla ve tek işlemde uygular (v2: oyunlar, kampanyalar,
gelen kutusu, kanal, içerik türü, arşiv, izleyici rolü…). Tablo yeniden kurulan adımlar yabancı anahtar
denetimiyle doğrulanır. Açılışta otomatik çalışır. Yeni şema değişikliği = yeni sürüm adımı +
`tests/fixtures/schema_v1.sql`'den geçiş testi. Yayımlanmış adımı düzenlemeyin.

## Geliştirme verisi ve mock modu

- `ETKILESIM_PROVIDER_MODE=mock`: platformlara bağlanılmaz, ölçümler `MOCK` kaynağıyla üretilir ve arayüzde
  **MOCK DATA** rozeti görünür.
- Sistem → *Boş veritabanına örnek veri ekle* (veya `python -m etkilesim seed-demo`): ekipler, kişiler,
  oyunlar, kampanyalar, paylaşımlar ve topluluklar. Yalnız boş veritabanına eklenir.
- Ortam değişkenleri: `.env.example`.

## Sayfa notları

Link eklerken **Sayfa hakkında not** alanına topluluğun kuralları, üyelerin tepkisi ve bir dahaki paylaşımda
dikkat edilecekler yazılır. Aynı topluluğu seçen herkes geçmiş kartında bu notları görür; not gönderi
ayrıntısından sonradan düzenlenebilir. Platform logoları `simple-icons` (CC0) paketinden derlemeye gömülür.

## İlk kullanım

1. **Ayarlar → Yönetici PIN'i**: en az 6 karakterlik PIN belirleyin. Ekip/kullanıcı ekleme, ayar
   değiştirme ve Telegram işlemleri PIN ister.
2. **Ekip & Uyarılar**: ekipleri ve kullanıcıları ekleyin. Uyarı almak için kişinin sayısal Telegram
   kimliği gerekir ve kişinin önce botunuza mesaj atmış olması gerekir. Ekip yöneticilerinin grubu
   için ekip sohbet kimliğini girin (grup kimlikleri `-` ile başlar).
3. **Ayarlar → Telegram botu**: BotFather'dan aldığınız jetonu girin (Windows Kimlik Yöneticisi'nde
   saklanır), test mesajı gönderin, sonra **Telegram bildirimleri açık** ayarını açın.
4. **Ayarlar → Tarayıcı oturumları**: X / Instagram / Facebook / Threads için kendi hesabınızla
   oturum açın (pencere açılır, giriş yapıp kapatın).
5. **Link ekle**: kullanıcı, link ve topluluk. Topluluk geçmişi kartı yakın zamanlı paylaşımları uyarır.

## Hatırlatma / uyarı kuralları (yönetici)

Ayarlar → *Hatırlatma ve uyarı (strike) kuralları* (genel veya ekip bazlı):

| Ayar | Varsayılan | Anlamı |
|---|---|---|
| Hareketsizlik eşiği | 3 gün | Bu kadar gün link eklemeyen kullanıcı uyarılır |
| Uyarılar arası süre | 24 saat | Bir sonraki uyarı için beklenen süre |
| İşaretlenmeden önce uyarı sayısı | 3 | Son uyarıda kullanıcı `İNCELEME GEREKLİ` olur, yöneticiye bildirilir |
| Günlük kontrol saati | 00:00 | Uygulama kapalıyken kaçan kontrol açılışta telafi edilir |

Kullanıcı yeni (güncel) bir link eklediğinde sayaç ve işaret sıfırlanır; geçmiş uyarılar silinmez.
**Elle tetikleme ve test** kartından kontrolü test saatiyle çalıştırabilirsiniz.

## Ölçüm nasıl çalışır, sınırları nelerdir

| Platform | Yöntem | Not |
|---|---|---|
| Reddit | Herkese açık `.json` | Skor, yorum sayısı, yorum metinleri; görüntülenme yok |
| Discourse forumları | `/t/…json` | Görüntülenme, beğeni, yanıt |
| YouTube / diğer siteler | JSON-LD / OpenGraph | Sayfanın verdiği kadar |
| X, Instagram, Facebook, Threads | Kendi oturumunuzla gerçek tarayıcı | Sayfa içi JSON durumu → yedek metin |

- **Bot korumaları atlatılmaz.** Giriş istenirse gönderi *Giriş gerekli*, CAPTCHA/hız sınırı
  görülürse *Veri alınamıyor* olur ve o platform bir süre (30 dk → 6 sa → 24 sa) denenmez.
- Ölçülemeyen linkler (örn. kişisel Facebook grupları) için gönderi ayrıntısından **elle sayaç** ve
  **elle yorum** girişi yapılır; bu değerler *Elle girildi* etiketiyle gösterilir.
- Bilinmeyen değer **"—"** olarak gösterilir, 0 olarak değil.
- Platform sayfa yapıları sık değişir; ayrıştırıcılar sentetik örneklerle test edilmiştir, gerçek
  hesaplarla doğrulanmamıştır.

## Test

```powershell
engine\.venv\Scripts\python.exe -m pytest engine     # motor
npx vitest run; npx tsc --noEmit; npm run lint        # arayüz
npm run e2e                                           # uçtan uca (demo derlemesi + sistemdeki Edge/Chrome)
npm run audit:deps                                    # npm audit + pip-audit
cd src-tauri; cargo test; cargo clippy --all-targets -- -D warnings
```

## Paketleme (Windows yükleyici)

```powershell
npm run app:release
```

Önce `scripts/build-engine.ps1` motoru PyInstaller ile `src-tauri/binaries/etkilesim-engine-x86_64-pc-windows-msvc.exe`
olarak paketler (PyInstaller'ı kurar), sonra Tauri NSIS yükleyicisi üretilir
(`src-tauri/target/release/bundle/nsis/`). Yayıncı bilgisi: *created by axthrowa*.
2026-10-09 bu makinede derlendi (yükleyici ~55 MB); paketlenmiş motor `health`, `seed-demo`, `analytics`, `export`, `backup` ile duman testinden geçti. Kurulumun kendisi ve tarayıcı oturumları elle denenmedi.

## Sorun giderme

- **"Motor bulunamadı"**: geliştirmede `engine\.venv` kurulu olmalı; sürüm paketinde
  `etkilesim-engine.exe` uygulama klasöründe olmalı. `ETKILESIM_ENGINE` ile yol verilebilir.
- **Günlükler**: `%LOCALAPPDATA%\EtkilesimTakip\engine.log` (JSON satırları, jetonlar temizlenmiş).
- **Bildirim gitmiyor**: Ayarlar'da bildirimler açık mı, jeton kayıtlı mı, kullanıcının Telegram
  kimliği var mı (*Hedef yok* durumu), kişi bota mesaj atmış mı? *Bildirim kuyruğu* hata ayrıntısını gösterir.
- **Vite EBUSY hatası**: `vite.config.ts` içinde `src-tauri/` ve `engine/` izlemeden çıkarılmıştır.

## Güvenlik ve gizlilik

- Yorum yazarları saklanmaz, `@etiket`ler maskelenir. Veriler yalnızca bu bilgisayarda tutulur.
- Bağlantılar özel/yerel ağ adreslerine yönlendirilemez (SSRF koruması, her yönlendirmede tekrar denetim).
- Yönetici PIN'i yerel bir arayüz kapısıdır; diske erişimi olan birine karşı güvenlik sınırı değildir.
