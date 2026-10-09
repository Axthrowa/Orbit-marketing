# CONTRIBUTING.md — Etkileşim Takip

Gerilla pazarlama takip, istatistik, duygu analizi ve topluluk keşif masaüstü uygulaması.
Orbit Marketing'in yerel (tek makine, SQLite) devamı. İmza: **created by axthrowa** (Cargo authors,
`tauri.conf.json` publisher/copyright, arayüz alt bilgisi, motor `health` yanıtı). Kaldırma.

## Mimari

```
React 18 + TS (src/)  ──invoke──▶  Tauri v2 kabuğu (src-tauri/)  ──stdin JSON──▶  Python motoru (engine/etkilesim)
   arayüz, durum yok              beyaz liste + PIN env + daemon         iş mantığı + SQLite (WAL)
                                                                         └─ daemon: APScheduler (ölçüm, 00:00 uyarı, keşif, Telegram)
```

- **İş mantığı yalnızca motorda.** Rust kabuğu yönlendirir; React yalnızca gösterir/çağırır.
- Motor sözleşmesi: `python -m etkilesim <komut>`; yük stdin'den JSON; yanıt stdout'ta
  `{"ok":true,"data":…}` / `{"ok":false,"error":{"code","message"}}`.
- Yeni motor komutu = `engine/etkilesim/cli.py` (`@command`) + `src-tauri/src/commands.rs`
  (`engine_commands!` satırı) + `src-tauri/src/main.rs` (`generate_handler!`) + `src/lib/engine.ts`.
  Rust testi üçünün uyumunu denetler. `daemon` asla arayüze açılmaz.
- Veri: `%LOCALAPPDATA%\EtkilesimTakip\` (`etkilesim.db`, `engine.log`, `browser-profile/`).
  `ETKILESIM_DATA_DIR` ile değiştirilebilir (testler bunu kullanır).

## Komutlar (depo kökünden)

| Amaç | Komut |
|---|---|
| Motor testleri | `engine\.venv\Scripts\python.exe -m pytest engine` |
| Motor lint/biçim/tip | `cd engine; .venv\Scripts\ruff check etkilesim tests; .venv\Scripts\ruff format --check etkilesim tests; .venv\Scripts\mypy` |
| Arayüz testleri | `npx vitest run` |
| Arayüz tip + yasak desen | `npx tsc --noEmit; node scripts/check-forbidden.mjs` |
| Rust testleri + clippy | `cd src-tauri; cargo test; cargo clippy --all-targets -- -D warnings` |
| Uçtan uca (E2E) | `npm run e2e` (demo derlemesi + `e2e/` Python Playwright, sistemdeki Edge/Chrome; tarayıcı indirmez) |
| Bağımlılık taraması | `npm run audit:deps` (npm audit + pip-audit) |
| Geliştirme | `npm run app:dev` (Vite 1420 + Tauri; motor `engine\.venv`'den çalışır) |
| Sürüm paketi | `npm run app:release` (PyInstaller motoru + NSIS yükleyici) |

Her değişiklikten sonra: biçim → lint → tip → test. Kırmızıyken bir sonraki işe geçme.

## Kodlama standartları

- Python 3.11+ (venv 3.14), `mypy --strict` temiz, `ruff` (satır 110). Saf fonksiyonlar test edilir;
  zaman `now` parametresiyle verilir (test saati). Zamanlar UTC ISO `YYYY-MM-DDTHH:MM:SSZ`.
- TS `strict` + `noUncheckedIndexedAccess`; `any`, `@ts-ignore`, boş `catch`, TODO yasak
  (`scripts/check-forbidden.mjs`). Renkler yalnızca `src/index.css` token'larından; bileşenlere ham
  renk yazma, durum tonu için `Badge`/`Alert` `tone` kullan.
- Görsel dil **Orbit Marketing Web v0.3.0** ile aynıdır (`Desktop\Orbit-Marketing-Web-v0.3.0\styles.css`,
  `theme.css`, `icons.js`): mor/mercan token'lar, üst başlık + simgeli yatay sekmeler, `kicker` +
  büyük başlık, 18px `panel`, `weekly-card`, Orbit çizgi simgeleri (`components/OrbitIcon.tsx`).
  Yeni ekran eklerken `Card kicker=… title=…` ve mevcut sınıfları kullan; yeni görsel dil icat etme.
- Rust: `unwrap`/`expect` yalnızca testlerde; hata `EngineFailure {code,message}`.
- Adlandırma: motor komutları kebab-case (`add-post`), Tauri komutları snake_case (`add_post`).
- Kullanıcıya dönük metinler Türkçe.

## Veritabanı

- Şema `engine/etkilesim/schema.sql` = v1 tabanı; sürüm `PRAGMA user_version`. Sonraki sürümler
  `engine/etkilesim/migrations.py` adımlarıdır (v2: oyun/kampanya/gelen kutusu/kanal/arşiv/viewer…).
  Şema değişikliği = yeni adım + `tests/fixtures/schema_v1.sql`'den geçiş testi. Yayımlanmış adımı veya
  `schema.sql`'i yerinde düzenleme. Tablo yeniden kuran adım sonunda `foreign_key_check` çalışır.
- Gönderiler silinmez, `archived_at` ile arşivlenir; tüm listeler/analitik arşivi dışlar.
- **Bilinmeyen sayaç `NULL`'dır, 0 değildir.** Arayüz "—" gösterir. Ölçümler
  `post_metric_snapshots`'a eklenir (üzerine yazılmaz); `posts.current_*` son bilinen değerdir.
- Yorum yazarı saklanmaz; `@etiket`ler maskelenir (`sentiment.mask_for_storage`).
- Hiçbir hata yolu gönderi silmez; durum `DATA_UNAVAILABLE` / `AUTHORIZATION_REQUIRED` olur.

## Uyarı (strike) sistemi

`strikes.run_inactivity_check(conn, now)`: eşik (`inactivity_days`) → uyarı 1..`max_strikes`,
uyarılar arası `strike_interval_hours` (5 dk tolerans), son uyarıda `flagged` + yönetici/ekip
Telegram eskalasyonu. Tekillik `strike_events(user_id, cycle_key, strike_number)` +
`notifications.dedupe_key`. Yeni güncel paylaşım sayaç/işareti sıfırlar, geçmişi silmez,
gönderilmemiş uyarı mesajlarını iptal eder. Eşikler genel veya ekip bazlı (`settings.SPECS`,
`team_overridable`). Bildirimler varsayılan kapalı; açılmadan önce birikenler toplu gönderilmez.

## Güvenlik kuralları

- **Platform korumaları atlatılmaz:** `playwright-stealth`, parmak izi taklidi, otomasyon bayrağı
  gizleme, CAPTCHA çözme, giriş duvarı aşma YOK. Tarayıcı yalnızca kullanıcının kendi oturumuyla
  (kalıcı profil) çalışır. Engel görülürse `providers.record_failure(blocked=True)` platformu duraklatır.
- Her dış URL `security.validate_public_url` ile denetlenir (özel/yerel ağ, file/javascript/data
  şemaları, kullanıcı bilgisi, standart dışı port engelli); HTTP yönlendirmelerinde ve tarayıcıda
  son adreste tekrar denetlenir.
- Yönetici PIN'i scrypt ile saklanır, 5 hatalı denemede 5 dk kilit; PIN motora yalnızca
  `ETKILESIM_ADMIN_PIN` ortam değişkeniyle gider (argv/günlük yok). Bu yerel bir kapıdır.
- Sırlar (Telegram jetonu, SMTP parolası, Teams webhook) yalnızca işletim sistemi kimlik deposunda
  (`keyring`, `secrets_store.SECRETS`); veritabanına, günlüğe, dışa aktarmaya yazılmaz; hata metinleri
  `secrets_store.redact` ile temizlenir. Telegram mesajları düz metin (parse_mode yok).
- Dışa aktarmada hücreler formül enjeksiyonuna karşı temizlenir (`maintenance._safe`).
- Önizleme/demo motoru (`src/lib/mock.ts`) ve motor mock sağlayıcısı (`ETKILESIM_PROVIDER_MODE=mock`)
  her zaman görünür biçimde etiketlenir (DEMO şeridi / MOCK DATA rozeti).
- SQL yalnızca parametreli; dinamik parça yalnızca sabit metinlerden kurulur (`# noqa: S608` gerekçeli).
- CSP sıkı (`tauri.conf.json`); harici kaynak yüklenmez.

## Sağlayıcı kuralları

- Öncelik: herkese açık JSON (Reddit `.json`, Discourse `/t/…json`) → JSON-LD/OpenGraph →
  kullanıcının kendi oturumuyla tarayıcı (X, Instagram, Facebook, Threads) → elle giriş.
- Ayrıştırıcılar (`parsers.py`) saftır ve sentetik fikstürlerle test edilir. Alan adları gerçek
  hesaplarla doğrulanmamıştır; platform değişince önce fikstür + test, sonra ayrıştırıcı.
- Topluluk Radarı yalnızca keşif/öneri yapar; otomatik paylaşım YOK.

## Yasak kısayollar

`any`, `@ts-ignore`, boş catch, sessiz hata, sabit parola/jeton, gerçek gibi gösterilen sahte veri
(önizleme motoru `src/lib/mock.ts` yalnızca `vite dev`'de yüklenir ve "DEMO" şeridi gösterir),
istenen iş yerine TODO, React bileşeninde veya Tauri komutunda iş mantığı, SQL'e değer
enterpolasyonu, bot korumasını atlatma.

## Windows tuzakları

- PowerShell 5.1 `Get-Content`/`Set-Content` UTF-8 dosyaları ANSI okur/BOM yazar → Türkçe karakterler
  bozulur (bir kez `collectors.py` bozuldu). Dosya düzenlemede Edit/Write aracını veya
  `encoding="utf-8"` kullanan Python betiğini kullan.
- Git Bash'ten Python'a heredoc ile Türkçe metin geçirme; betiği dosyaya yaz.
- Vite `src-tauri/` ve `engine/`'i izlememeli (kilitli `target/*.dll` EBUSY ile çökertir).
- Depo yolu boşluk ve `ş` içerir; `npm exec` yerine `node node_modules/vite/bin/vite.js` tercih et.
