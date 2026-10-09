# Master prompt (GUERILLA MARKETING INTELLIGENCE PLATFORM) — boşluk analizi ve plan

Tarih: 2026-10-06 · created by axthrowa

Master prompt'un 108 bölümü, depodaki gerçek kodla tek tek karşılaştırıldı. Durumlar:

- **Var**: uygulanmış ve testli.
- **Kısmi**: bir bölümü var; eksik kısmı bu planda.
- **Yok**: hiç yok; bu planda yapılacak.
- **Yerine geçti**: kullanıcının sonraki açık kararı bu maddenin yerine geçti (aşağıda gerekçe). Yeniden
  yazılmaz; maddenin *amacı* mevcut mimaride karşılanır.

## Sonraki kararların yerine geçtiği maddeler

Master prompt'tan sonra kullanıcı şunları açıkça seçti: (1) "Orbit üzerinden ilerleyelim", (2) ikinci
prompt: **Tauri v2 + React + Python + yerel SQLite (WAL) + Telegram**, (3) "API erişimim yok",
(4) "kullanıcı hesabından açılsın, yönetici için PIN istesin". Bu yüzden:

| Master prompt | Yerine geçen karar | Amacın karşılanma şekli |
|---|---|---|
| §4 FastAPI + PostgreSQL + Redis + Celery, §83 Docker | Yerel SQLite + Python motoru + APScheduler daemon | Migration'lı SQLite (WAL), tek örnek zamanlayıcı, iş kayıtları |
| §5 e-posta/şifre + Argon2id, JWT, Entra ID | Yerel hesap seçimi + yönetici PIN'i (scrypt, kilitlenme) | PIN yalnız ortam değişkeniyle motora gider |
| §7 çok kiracılı organizasyon | Tek kurulum, çok ekip | `teams` + ekip bazlı kurallar |
| §19–20 resmî platform API'leri | "API erişimim yok" | Herkese açık JSON/JSON-LD + kendi oturumla tarayıcı + elle giriş |
| §64–65 `/api/v1` HTTP + WebSocket | Masaüstü: Tauri IPC + motor CLI sözleşmesi | Beyaz listeli komutlar; sözleşme sürümü `api_version: v1` |
| §66 Redis önbellek | Yerel tek kullanıcı | Gerek yok (sorgular yerel SQLite) |
| §76–77 /health, Prometheus uç noktası | HTTP sunucusu yok | `health` ve `metrics` (Prometheus metin biçimi) motor komutları |

## Madde madde durum

| § | Konu | Durum | Not / yapılacak |
|---|---|---|---|
| 0 | Tip güvenliği, strict TS, migration, log, retry, rate limit, audit, gizli saklama, test, health, provider soyutlama, zarif bozulma | Kısmi | **Pydantic** yok (elle doğrulama). Migration yalnız v1 → **sürümlü migration altyapısı (P1)**. API sürümü → `api_version` (P9) |
| 1 | Hangi oyun/kampanya, içerik türü, platform ROI, topluluğa hangi oyun | **Yok** | Oyun/kampanya/içerik türü yok → **P2, P3, P4** |
| 2–3 | Mimari, React+TS+Tailwind+Lucide | Var | TanStack/Recharts/Zustand yerine sade React (bilinçli; bağımlılık az) |
| 6 | 5 rol (SUPER_ADMIN…VIEWER) | Kısmi | admin/manager/member var; **viewer** rolü ve **ekip yöneticisi görünümü** yok → **P2** |
| 8–10 | users/games/campaigns tabloları | Kısmi | **games, campaigns yok**; users.email yok → **P1/P2** |
| 11 | posts alanları | Kısmi | game_id, campaign_id, content_type, archived_at (soft delete) yok → **P1** |
| 12 | Zaman serisi metrik | Var | |
| 13 | Türetilmiş metrikler (velocity 1h/6h/24h, growth, performance_score) | **Yok** | → **P3** |
| 14–15 | Yorumlar, duygu, model adı | Var | Yazar hiç saklanmaz (hash'ten de güçlü gizlilik) |
| 16 | Topluluk alanları (dil, spam riski, son tarama, kategori) | Kısmi | → **P1/P4** |
| 17–18 | Topluluk geçmişi, posting-context, ayarlanabilir eşikler | Var | geçmişe kampanya eklenecek (P2) |
| 21 | Adaptif ölçüm takvimi (+1/+3/+6/+12/+24 sa, sonra günlük, 7g→48 sa, 30g→haftalık) | Kısmi | Sabit aralık var → **adaptif mod (P9)** |
| 22 | İş kayıtları (durum, deneme, hata) | Kısmi | `job_runs` var; **iş ekranı, elle çalıştır/yeniden dene yok** → **P7** |
| 23–24 | 429 geri çekilme, devre kesici | Var | Durum adları (CLOSED/OPEN/HALF_OPEN) ekranda gösterilecek (P7) |
| 25–27 | Yorum sınırı, tekillik, duygu hattı, skor | Var | |
| 28 | Konu analizi altyapısı | **Yok** | → **P5** (bug/fiyat/performans/sunucu/oynanış/grafik/istek) |
| 29–30 | Topluluk keşfi, sorgu üretimi | Var | |
| 31–32 | Öneri skoru formülü (0.30/0.20/0.20/0.10/0.10/0.10 − spam − yakınlık) + öneri nedenleri | **Yok** | Basit 0.7/0.3 var → **P4** |
| 33 | Otomatik paylaşım yok | Var | |
| 34–38 | 3 uyarı motoru, sıfırlama, warning_events | Var | |
| 39–42 | Kanallar IN_APP / EMAIL / TEAMS | Kısmi | Telegram var; **uygulama içi okunmamış rozeti/okundu yok, e-posta yok, Teams yok** → **P6** |
| 43 | 3. uyarıda yönetici eskalasyonu | Var | e-posta/Teams'e de gidecek (P6) |
| 44–46 | Performans motoru, ayarlanabilir ağırlıklı normalize skor, liderlik tablosu + filtreler | **Yok** | → **P3** |
| 47–49 | Pano KPI'ları, platform dağılımı/performansı, kullanıcı panosu (benim performansım, önerilen topluluklar) | Kısmi | → **P3** |
| 50 | Formda kampanya, oyun | **Yok** | → **P2** |
| 51–53 | SSRF, hat, topluluk uyarı kartı | Var | karta kampanya eklenecek (P2) |
| 54 | Gönderi ayrıntısı | Kısmi | kampanya/oyun başlıkta (P2) |
| 55 | Radar sütun/aksiyonlar | Var | kategori/dil gösterimi (P4) |
| 56 | Yönetici paneli bölümleri | Kısmi | **Kampanyalar, Oyunlar, Performans, Uyarılar, İşler, Denetim günlüğü, Sağlayıcılar** → **P2, P3, P7** |
| 57 | Sağlayıcı sağlığı (başarı %, devre durumu) | Kısmi | → **P7** |
| 58–59 | İş ekranı, elle yeniden deneme | **Yok** | → **P7** |
| 60 | Denetim günlüğü | Kısmi | Kayıt var, **ekran yok** → **P7** (IP/UA: yerel uygulamada anlamsız; aktör kaydedilir) |
| 61 | Güvenlik (bağımlılık taraması dahil) | Kısmi | **Bağımlılık taraması** yok → **P10** |
| 62 | Sır saklama | Var | |
| 63 | Saklama süreleri (yorum 180 g, audit 365 g) | **Yok** | → **P8** |
| 67 | Genel arama | **Yok** | → **P8** |
| 68 | Analitik filtreleri (tarih, platform, kampanya, oyun, kişi, ekip, topluluk) | **Yok** | → **P3** |
| 69 | Dışa aktarım CSV/XLSX/JSON | **Yok** | → **P8** |
| 70–74 | Tasarım, tema, renk token'ları, hata UX'i | Var | (Orbit görsel dili) |
| 75 | Yapılandırılmış log, request_id, job_id | Var | |
| 78 | Playwright E2E | **Yok** | → **P9** |
| 79 | Kritik test senaryoları | Var | |
| 80 | İdempotentlik | Var | gönderi/bildirim/uyarı/metrik tekilliği |
| 81 | Soft delete | **Yok** | gönderi arşivleme → **P2** |
| 84 | `.env.example` | **Yok** | → **P9** |
| 89 | Provider mock modu + "MOCK DATA" rozeti | Kısmi | Arayüz demo motoru var; **motor tarafı mock sağlayıcı yok** → **P9** |
| 90 | Geliştirme tohum verisi (1 org, 2 ekip, 5 kişi, 3 oyun, 4 kampanya, 30 gönderi, 20 topluluk…) | **Yok** | → **P9** |
| 93 | PostgreSQL yedekleme dokümanı | Yerine geçti | **SQLite yedekleme komutu + doküman** → **P8** |
| 106 | README bölümleri (Teams kurulumu vb.) | Kısmi | → **P10** |
| 107 | Windows yükleyici + "created by axthrowa" | Kısmi | yapılandırma hazır, **derlenmedi** → **P10** |

## Plan (bağımlılık sırası)

| Faz | İçerik | Doğrulama |
|---|---|---|
| **P1** | Sürümlü migration altyapısı (v1→v2, tablo yeniden kurma dahil); `games`, `campaigns`, `inbox`; posts.game_id/campaign_id/content_type/archived_at; users.email + `viewer` rolü; communities.language/spam_risk/last_scanned_at; comments.topics; notifications.channel; snapshot kaynağı `MOCK` | v1 fikstüründen geçiş testi |
| **P2** | Oyun/kampanya yönetimi (motor + CLI + ekran), formda oyun/kampanya/içerik türü, geçmiş kartında kampanya, gönderi arşivleme (soft delete), viewer rolü salt-okunur, ekip yöneticisi görünümü | birim + arayüz testleri |
| **P3** | Analitik: velocity/growth, ayarlanabilir ağırlıklı performans skoru, liderlik tablosu, platform/içerik türü/kampanya/oyun performansı, dönem ve filtreler, "Benim performansım" | birim + arayüz |
| **P4** | Topluluk öneri skoru (6 bileşen − spam − yakınlık) + "Önerilme nedeni" maddeleri, oyun↔topluluk eşleşmesi, dil uyumu | birim |
| **P5** | Konu analizi (yorumlarda konu etiketleri) + Oyuncunun sesi'nde konu dağılımı | birim + arayüz |
| **P6** | Uygulama içi gelen kutusu (okunmamış rozeti, okundu, tümünü okundu); e-posta (SMTP, şifre kimlik deposunda) ve Microsoft Teams (Workflows webhook, kimlik deposunda) kanalları; kanal bazlı yeniden deneme | birim (sahte gönderici) |
| **P7** | Sistem ekranı: işler (geçmiş, şimdi çalıştır, başarısızı yeniden dene), sağlayıcı sağlığı (başarı %, CLOSED/OPEN/HALF_OPEN), denetim günlüğü, uyarı geçmişi | birim + arayüz |
| **P8** | Genel arama, dışa aktarım (CSV/XLSX/JSON), SQLite yedekleme + geri yükleme dokümanı, saklama süresi temizliği (zamanlayıcı işi) | birim |
| **P9** | Adaptif ölçüm takvimi, motor mock sağlayıcı modu (`ETKILESIM_PROVIDER_MODE=mock`, "MOCK DATA" rozeti), `seed-demo`, `metrics` (Prometheus metni), `api_version`, `.env.example`, Playwright E2E | birim + E2E |
| **P10** | Bağımlılık taraması (pip-audit, npm audit), README tamamlama, PyInstaller motor + NSIS yükleyici derleme | derleme çıktısı |

## Durum (2026-10-09)

| Faz | Durum | Nerede |
|---|---|---|
| P1 | ✅ Tamam | `migrations.py` (v2), `tests/test_migrations.py` (v1 fikstüründen geçiş) |
| P2 | ✅ Tamam | `catalog.py`, Kampanyalar sekmesi, Paylaşımlar formunda kampanya + içerik türü, gönderi ayrıntısında arşivle, izleyici salt okunur, ekip yöneticisi kullanıcı hesabında ekibinin tamamını görür |
| P3 | ✅ Tamam | `analytics.py`, Analitik sekmesi (dönem/kampanya/oyun/platform filtreleri, kırılımlar, lider tablosu, ayarlı ağırlıklar); kullanıcı hesabında "benim performansım" |
| P4 | ✅ Tamam | `recommend.py`, Topluluk keşfi: oyun/kampanya hedefi, öneri puanı, artı/eksi gerekçeler |
| P5 | ✅ Tamam | `topics.py`, Oyuncunun sesi ve Analitik'te konu dağılımı, gönderi ayrıntısında yorum konuları |
| P6 | ✅ Tamam | `inbox.py`, `notify.py` (Telegram/e-posta/Teams), Bildirimler: gelen kutusu + okunmamış rozeti; Ayarlar: e-posta/Teams grubu ve sır kartı |
| P7 | ✅ Tamam | `system.py`, Sistem sekmesi (işler + şimdi çalıştır, sağlayıcı devre durumu, yeniden dene, denetim, uyarı geçmişi) |
| P8 | ✅ Tamam | `search.py` + üst başlıkta genel arama, `maintenance.py` (dışa aktarma, yedek, saklama), README yedek/geri yükleme |
| P9 | ✅ Tamam | adaptif takvim, `mockprovider.py` + MOCK DATA rozeti, `seed-demo`, `metrics`, `api_version`, `.env.example`, `e2e/test_demo_e2e.py` (Playwright, sistem Edge/Chrome) |
| P10 | ✅ Tarama + README; yükleyici için bkz. README > Paketleme | `npm audit` 0 açık (vitest 3→5), `pip-audit` bilinen açık yok |

Bilinçli sapmalar (değişmedi): playwright-stealth / parmak izi taklidi / CAPTCHA çözme yok (ADR-013);
PostgreSQL/FastAPI yerine yerel SQLite + Tauri; RBAC yerel PIN kapısıdır, çok makineli hesap sistemi değildir;
ayrıştırıcılar ve Telegram/e-posta/Teams teslimatı gerçek hesaplarla doğrulanmadı.
