# Guerilla Marketing Intelligence — Analiz ve Mimari Karar Kaydı (ADR)

Durum: **TASLAK — kullanıcı onayı bekliyor.** Kod yazılmadı.
Tarih: 2026-10-05 · created by axthrowa

---

## A. Repository Analizi

### A.1 Ne bulundu

`Etkileşim takip` klasörü boştu. Ama masaüstünde aynı problemi çözen, çalışan bir ürün var: **Orbit Marketing** (v0.3.0). Bu analiz onun üzerine kurulu. Master prompt §0 "çalışan yapıları sebepsiz yeniden yazma" dediği için bu kritik.

| Konum | Ne | Not |
|---|---|---|
| `Documents/ChatGPT/marketing/` | **Orbit'in gerçek kaynak deposu** (`.git` var): `orbit-desktop/` (**Tauri** `src-tauri/` + `ui/` + Python `backend.py`, PyInstaller `orbit-backend.spec`), `orbit-cloud/`, `marketing_tracker/`, `supabase/` | İlk taramada gözden kaçtı, sonradan bulundu. Henüz **satır satır incelenmedi** |
| `Orbit-Marketing-Workspace-v0.3.0/` | Derlenmiş dağıtım paketi (Portable.exe ~20 MB) + `supabase/` kopyası | Kaynak değil, çıktı |
| `Orbit-Marketing-Web-v0.3.0/` | Web sürümü, düz JS (`analytics.js`, `integrations.js`, `campaigns.js`, `session.js`…) | Derleme adımı yok, TypeScript değil |
| `supabase/migrations/*.sql` (4 dosya) | Gerçek şema, RLS, RPC fonksiyonları | Tek doğruluk kaynağı |
| `supabase/functions/orbit-worker/` | Deno/TS Edge worker (`index, domain, meta, threads, notifications, delivery`) | pg_cron her 5 dk `tick` çağırıyor |
| `orbit-data/Marketing.xlsx` | Başlık: **Kişi · Oyun · Platform · Marketing Türü · Tarih · Bağlantı** | **Sadece başlık satırı, veri yok** |
| `orbit-data/state/marketing_tracker.db` | SQLite: `app_users`, `app_sessions`, `login_attempts` | 0 satır, eski yerel mod kalıntısı |
| `Projeler/` | StreamAxT (yayın botu) | **Alakasız**, dokunulmadı |

### A.2 Excel dosyası sorunu (dürüst durum)

Mesajındaki `bugreport\Başlıksız e-tablo.xlsx` **diskte yok**: `bugreport` klasörü masaüstünde bulunmuyor ve tüm kullanıcı profilinde o ada sahip dosya çıkmadı. Bu yüzden **"Bağlantı sütunundaki marketing ne kadar etkileşim aldı" analizi yapılamadı**. Rakam uydurmadım.
`Marketing.xlsx` şeması senin tablonla birebir aynı (Bağlantı sütunu dahil), yani muhtemelen aynı veri. Dosyayı yeniden verirsen link sayısı, platform/kişi/oyun kırılımı ve hangi linklerin otomatik ölçülebildiği çıkarılır.

### A.3 Orbit'in mevcut yetenekleri (okunan koda dayalı)

**Var ve çalışıyor (kaynak testi iddiası, canlı doğrulama yok):**

- Auth: Supabase Auth, doğrulanmış e-posta. Roller: yalnızca `admin` / `user`. RLS her tabloda; rol `orbit_role()` ile korunan DB durumundan okunuyor.
- Post kaydı: `orbit_posts` (url, platform, activity_date, `unique(person,url)`), `orbit_add_post` RPC, advisory lock ile yarış koruması.
- **3 aşamalı hatırlatma + yönetici eskalasyonu zaten var:** `orbit_generate_reminders` (eşik `inactivity_days`=7, kişi bazlı override, 09:00/13:00/17:00 slotları, 3. hatırlatmada `escalation` bildirimi, yeni post gelince trigger ile sıfırlama, `dedupe_key` ile idempotentlik). Europe/Istanbul saatiyle.
- Teslimat: `orbit_notices` → `orbit_deliveries` outbox, Teams Workflows webhook hedefleri (Secret adıyla), Gmail SMTP (TLS 465), varsayılan **kapalı** + "etkinleştirme öncesi bildirimler toplu gitmez" koruması.
- Ölçüm sağlayıcıları: YouTube Data API (video istatistikleri), Meta Graph (yetkili Facebook Sayfası / profesyonel Instagram, son 50 gönderi, ≤25 yorum), Threads API. Bilinmeyen değer **0 gösterilmiyor** ("—"). Kişisel FB/IG linkleri için manuel alan var.
- Topluluk keşfi: Brave Search + YouTube kanalları, skor/neden/boyut bandı, `new/shortlisted/dismissed`.
- Analiz UI: haftalık grafik, grup/platform kırılımı, erişim/etkileşim, yorum duygu özeti (**istemci tarafı kural tabanlı**, "Sunucu analizi bekleniyor" notu var).
- Güvenlik: anon erişim yok, service_role istemciye gitmiyor, job secret Vault'ta, hata ayrıntısında gizli değer dönmüyor.

### A.4 Master prompt ile boşluk analizi

| Master prompt gereksinimi | Orbit durumu | Boşluk |
|---|---|---|
| Time-series metrik (§12) | `orbit_posts.metric` **jsonb üzerine yazılıyor** | **Büyük.** Geçmiş yok, velocity/growth hesaplanamaz |
| Yorum tablosu + pseudonymize (§14) | `comments_data` jsonb, post içinde | Ayrı tablo, hash, retention yok |
| Sentiment (§15, §26) | İstemci kuralları | Sunucu tarafı çok dilli model yok |
| Organization/Team/Game/Campaign (§7–11) | `marketing_data` (kampanya adı+bütçe), oyun/tür `annotation` jsonb içinde | Normalize tablolar yok, `organization_id` yok |
| 5 rol RBAC (§6) | 2 rol | Manager/Viewer/Super admin yok |
| Audit log (§60) | Yok | Eksik |
| Community post history / duplicate control (§17–18) | Yok, topluluk ↔ post bağı yok | Eksik |
| Recommendation score (§31) | Tek `score` alanı, formül dokümante değil | Bileşenli skor + açıklama + recency cezası |
| Bildirim kanalları IN_APP/EMAIL/TEAMS (§39) | Teams+Email var, in-app okunma (`orbit_notice_reads`) var | Realtime bell, kanal modeli |
| Rate limit/circuit breaker (§23–24) | Worker'da deneme sayacı var | Provider başına durum yok |
| Idempotency key (§80) | `dedupe_key` + unique | API seviyesinde key yok |
| Mock mode (§89), health, Prometheus (§75–77) | Yok | Eksik |
| Test kapsamı | Kaynak testleri var, repo içinde bulunmadı | Doğrulanamadı |

### A.5 Mimari sorunlar

1. Metrik üzerine yazma (A.4) → en önemli veri modeli hatası.
2. Kaynak repo `Documents/ChatGPT/marketing` altında, dağıtım klasörleri masaüstünde: **iki kopya** var (`supabase/` ve kurulum dokümanları her ikisinde de). Tek kaynağa indirilmeli; hangisinin güncel olduğu Faz 0'da diff ile doğrulanacak.
3. Web sürümü TypeScript'siz, derlemesiz; `cloud.bundle.js` 827 KB üretilmiş dosya.
4. İki "veri dünyası": eski yerel SQLite/Excel modu ve yeni Supabase bulutu. Excel içe aktarma var ama ikisi paralel yaşıyor.
5. Eşik kuralı master prompt'tan farklı (A.6).

### A.6 Master prompt içi çelişkiler / netleştirilmesi gerekenler

- **Uyarı aralığı:** prompt §34 "warning_interval = 24 saat". Orbit ise aynı gün içinde 3 slot (09/13/17) kullanıyor, yani 3 uyarı ~8 saatte biter. Hangisi istendiği belirsiz.
- **Eşik:** prompt 3 gün, Orbit 7 gün.
- **Tauri:** Orbit masaüstü zaten Tauri. Ancak yanında Python (`backend.py`, yerel SQLite/Excel modu) var; prompt'un "iş mantığı Tauri'ye gömülmez" kuralı için bu yerel backend'in rolü Faz 0'da netleştirilecek.
- **Facebook/Instagram kişisel link** ölçümü: prompt'un kendi kuralı (resmî API, bypass yok) gereği **otomatik ölçülemez**. Orbit de aynısını söylüyor. "Her bağlantının etkileşimi" hedefi bu yüzden platform bazında kısmi kalır (bkz. G).

---

## B. Architecture Decision Record

### ADR-001 — Orbit'i evrimleştir, sıfırdan yazma  *(KARAR BEKLİYOR, öneri: evrimleştir)*

| Seçenek | Artı | Eksi |
|---|---|---|
| **1. Orbit'i genişlet** (Supabase Postgres + RLS + Edge worker) | Çalışan auth/RLS/outbox/hatırlatma korunur; haftalar kazanılır; hosting ücretsiz katman | Master prompt'un FastAPI/Celery/Alembic/Tauri yığını kullanılmaz; ML için ek servis gerekir |
| **2. Master prompt yığını (greenfield)** | Prompt'a birebir uyum | Çalışan 3-uyarı/outbox/RLS yeniden yazılır; veri taşıma; aylar; §0 ile çelişir |
| **3. Hibrit (öneri)** | Veri+auth+bildirim Orbit/Supabase'te kalır; **yalnızca** sentiment/ağır analitik için küçük Python (FastAPI) servisi eklenir | İki çalışma zamanı |

**Öneri: Seçenek 3.** Gerekçe: eksikler (A.4) çoğunlukla *veri modeli* ve *analitik*; bunlar migration + yeni worker adımlarıyla kapanıyor. Python yalnızca Edge Function'ın barındıramadığı yerel NLP için.

### ADR-002 — PostgreSQL kalır, migration aracı Supabase SQL migration'ları
Seçenek 3'te Alembic yalnızca Python servisinin kendi (ayrı şemalı) tabloları için. Ortak şema tek yerde (Supabase migration) tanımlanır. Her değişiklik yeni numaralı migration (`2026100xNNNN_*.sql`); mevcut 4 dosyaya dokunulmaz.

### ADR-003 — Metrikler append-only `post_metric_snapshots`
`orbit_posts.metric` kalır (son değer önbelleği, geriye uyum), her ölçüm ayrıca snapshot satırı. `unique(post_id, provider, captured_at-bucket)` ile aynı snapshot iki kez yazılmaz. **Bilinmeyen = NULL** (0 değil), UI "—" göstermeye devam eder.

### ADR-004 — Çok kiracılık: `organization_id` şimdi eklenir
Varsayılan tek organizasyon oluşturulur, mevcut satırlar backfill edilir, RLS `organization_id` + rol ile genişler. SaaS olmasa bile maliyeti düşük, sonradan eklemek pahalı.

### ADR-005 — RBAC 2 → 5 rol, geriye uyumlu
`admin→ADMIN`, `user→USER` eşlemesi; `MANAGER`, `VIEWER`, `SUPER_ADMIN` eklenir. `orbit_role()` korunur, kontrol kümesi genişler. Rol değişimi yalnızca SUPER_ADMIN, audit'e yazılır.

### ADR-006 — Bildirim: mevcut outbox modeli korunur
`orbit_notices` + `orbit_deliveries` doğru desen (idempotent, claim/lease, retry). Eklenecek: `channel` ve `warning_events` ayrı kaydı, in-app için Supabase Realtime. **Teams: Workflows webhook varsayılan kalır**; Microsoft Graph (Activity Feed) Entra uygulama onayı ister, "hazır arayüz" olarak bırakılır, ilk sürümde zorunlu değil.

### ADR-007 — Hatırlatma politikası ayarlanabilir
`warning_interval_mode = SAME_DAY_SLOTS | EVERY_24H` ayarı. Varsayılan Orbit'in mevcut davranışı (kullanıcı beklentisini bozma). `inactivity_days` varsayılanı: **kullanıcıya soruluyor** (3 mü 7 mi).

### ADR-008 — Sentiment: ayrı Python servisi, yerel model
Edge Function (Deno, sınırlı süre/bellek) transformer çalıştıramaz. FastAPI + ONNX/Transformers servisi; yorum + sonuç tablosu DB'de, model adı/sürümü kayıtlı. Türkçe+İngilizce çok dilli model, **lisansı seçim anında doğrulanacak**. Emoji korunur. Model yoksa mevcut kural tabanlı sonuç `model_name='rules-v1'` olarak işaretlenip "düşük güven" gösterilir (graceful degradation).

### ADR-009 — Provider soyutlaması worker içinde
Mevcut `meta.ts`, `threads.ts`, YouTube kodu ortak `PlatformProvider` arayüzü arkasına alınır (validate/resolve/fetchMetrics/fetchComments/health). Veri kaynağı alanı: `OFFICIAL_API | AUTHORIZED_ACCOUNT | PUBLIC_ENDPOINT | RSS | OEMBED | PUBLIC_HTML | MANUAL`. Veri alınamayınca `DATA_UNAVAILABLE` / `AUTHORIZATION_REQUIRED`, post asla silinmez.

### ADR-010 — İstemci: mevcut Tauri kabuğu korunur
Orbit masaüstü zaten Tauri; yeniden yazılmaz. Yeni ekranlar `ui/` ve web sürümüne (TypeScript'e aşamalı geçişle) eklenir. Tauri v2 olup olmadığı `tauri.conf.json` ile Faz 0'da doğrulanır. İş mantığı Supabase RPC/worker'da kalır, Tauri/Python yerel katmanı ince tutulur.

### ADR-011 — Otomatik paylaşım yok
Community Radar yalnızca keşif/öneri/geçmiş kontrolü. Orbit zaten "kendi kendine reklam paylaşmaz"; korunur.

### ADR-012 — Kapsam dışı (bilinçli)
Login duvarı aşma, CAPTCHA/anti-bot atlatma, kişisel FB/IG scraping: yok. Kapsanmayanlar manuel giriş yoluyla gelir.

---

## C. Hedef Repository Ağacı (Seçenek 3)

```
etkilesim-takip/                      # yeni ana repo (Orbit kaynakları buraya alınır)
├─ CONTRIBUTING.md  README.md  .env.example  docker-compose.yml
├─ docs/  (00-analiz-ve-ADR.md, api.md, threat-model.md, backup.md)
├─ apps/
│  ├─ web/                            # Orbit Web v0.3.0 → TS'e aşamalı
│  │   src/{screens,components,lib/api,lib/tokens,state}/  tests/
│  ├─ desktop/                        # mevcut paket sarmalayıcı (Tauri opsiyonel faz)
│  └─ intelligence/                   # Python 3.12, FastAPI (yalnız NLP/ağır analitik)
│      app/{main.py,core/,schemas/,ml/{sentiment,preprocessing,language}.py,jobs/}
│      alembic/  tests/  pyproject.toml
├─ supabase/
│  ├─ config.toml  schedule.sql
│  ├─ migrations/    (mevcut 4 + yeni, numaralı, değişmez)
│  ├─ functions/orbit-worker/
│  │   index.ts  providers/{base,youtube,meta,threads,reddit,discourse,x,generic_forum,mock}.ts
│  │   jobs/{metrics,comments,inactivity,discovery,reports}.ts
│  │   notifications/{in_app,email,teams}.ts  lib/{ssrf,ratelimit,circuit}.ts
│  └─ seed/ (geliştirme seed, MOCK işaretli)
├─ packages/shared-types/             # DB'den üretilen tipler
├─ infra/{docker,backup}/
└─ tests/{unit,integration,e2e(playwright),rls}/
```

Yeni dosya yalnızca gerçekten gerektiğinde; mevcut `orbit-worker/*.ts` yerinde genişler.

---

## D. Veritabanı ER Modeli

**Korunan (Orbit):** `orbit_profiles` (=users), `orbit_members`, `orbit_posts`, `orbit_settings`, `orbit_communities`, `orbit_discovery_runs`, `orbit_notices`, `orbit_notice_reads`, `orbit_reminder_cycles`, `orbit_job_locks`, `orbit_teams_targets`, `orbit_deliveries`, `orbit_delivery_control`, `marketing_data`.

**Eklenen:**

```
organizations 1─* teams 1─* orbit_profiles(+organization_id, team_id, role5, last_post_at, flagged_at)
organizations 1─* games 1─* campaigns
organizations 1─* orbit_posts (+organization_id, game_id, campaign_id, community_id, platform_enum,
                               platform_post_id, provider_status, next_metrics_at)
orbit_posts 1─* post_metric_snapshots (likes, comments, shares, views NULLable, reposts, bookmarks, followers_at_capture, captured_at, provider, source_kind)
orbit_posts 1─1 post_analytics (engagement_rate, velocity_1h/6h/24h, growth*, sentiment_*, performance_score)
orbit_posts 1─* comments (platform_comment_id, author_hash SHA-256, text, language, collected_at)  unique(platform,platform_comment_id)
comments 1─1 comment_sentiments (label, scores, model_name, model_version)
orbit_communities (+organization_id, member_count, language, categories[], activity/relevance/quality/spam scores, status)
orbit_communities 1─* community_post_history (community_id, user_id, campaign_id, post_id, posted_at)
orbit_profiles 1─* warning_events (warning_number, reason, triggered_at, notification_id, resolved_at)  unique(user_id, cycle_key, warning_number)
orbit_notices (+channel, organization_id)
jobs (job_id, type, status, attempt, max_attempt, started/completed_at, error)
provider_state (provider, rate_limit_state, circuit_state, consecutive_failures, opened_at, last_success/failure)
audit_logs (actor, action, entity_type/id, old/new jsonb, ip, user_agent, ts)
settings_retention, idempotency_keys (key, route, response_hash, created_at)
```

Zorunlu index'ler prompt §82'deki listeyle aynı. Pagination zorunlu (25 / max 100). Silme gereken yerde `deleted_at`.
**Dashboard performansı:** ham snapshot taranmaz; `post_analytics` ve günlük özet tabloları pg_cron ile hesaplanır.

---

## E. API Sözleşmesi (`/api/v1`)

Orbit bugün RPC + PostgREST kullanıyor. İki katman:

1. **Supabase RPC/PostgREST** (veri, RLS korumalı) — mevcut `orbit_*` fonksiyonları korunur, yenileri eklenir.
2. **Intelligence servisi (FastAPI)** — yalnız ML ve ağır analitik, JWT doğrulaması Supabase anahtarıyla.

| Alan | Endpoint |
|---|---|
| Auth | `POST /auth/login` · `POST /auth/refresh` (Supabase Auth'a devredilir) · `GET /users/me` |
| Posts | `GET/POST /posts` (Idempotency-Key) · `GET /posts/{id}` · `/metrics` · `/comments` |
| Communities | `GET /communities` · `/recommendations` · `/{id}/posting-context` · `POST /{id}/favorite|block|use` |
| Analytics | `GET /analytics/dashboard|users|platforms|campaigns|communities` (filtre: tarih, platform, kampanya, oyun, kullanıcı, takım, topluluk) |
| Notifications | `GET /notifications` · `POST /{id}/read` · `POST /read-all` |
| Admin | `/admin/users|jobs|providers|audit-logs|settings` · `POST /admin/jobs/{id}/retry|cancel` · `POST /admin/jobs/retry-failed` · `POST /admin/export` (CSV/XLSX/JSON, async) |
| Sağlık | `/health/live` · `/health/ready` (PG+Redis*; provider kesintisi readiness'i bozmaz) · `/metrics` (Prometheus) |
| Gerçek zamanlı | Supabase Realtime: `metrics.updated post.updated notification.created warning.created user.flagged job.failed` |

\* Redis yalnızca Intelligence servisi ayağa kalkarsa; Orbit tarafında cache Postgres'te (aşağıda).

`posting-context` önerisi: `AVOID 0–3g · RECENTLY_USED 4–7g · CAUTION 8–14g · SAFE 15g+` (ayar tablosundan).

---

## F. Arka Plan İş Tasarımı

**Zamanlayıcı:** pg_cron her 5 dk → Edge `tick` (mevcut). `orbit_job_locks` + advisory lock tek-çalıştırıcıyı garanti eder (mevcut desen).

**Yaşam döngüsü:** `queued → running → succeeded | retrying → failed → dead_letter`. Her iş: `job_id, status, attempt, max_attempt, started_at, completed_at, error`.

| İş | Tetik | Not |
|---|---|---|
| FETCH_POST_METRICS | post eklenince hemen, sonra +1s,+3s,+6s,+12s,+24s, sonra 24s; >7g 48s; >30g haftalık | `next_metrics_at`; ayarlanabilir |
| FETCH_POST_COMMENTS | metrik sonrası | varsayılan 100; 20/50/100/250/500; sayfalı; `unique(platform,platform_comment_id)` |
| ANALYZE_SENTIMENT | yeni yorum | Intelligence servisi; yorum başına tek analiz |
| CALCULATE_ANALYTICS | saatlik | `post_analytics`, liderlik tablosu önbelleği |
| DISCOVER_COMMUNITIES | `discovery_interval_hours` | mevcut |
| CHECK_INACTIVITY | tick | mevcut `orbit_generate_reminders` genişler |
| SEND_NOTIFICATION | outbox claim | mevcut `orbit_claim_deliveries` |
| GENERATE_DAILY/WEEKLY_REPORT | cron | |

**Retry/backoff:** HTTP 429 → `Retry-After` varsa o, yoksa 30 sn → 1 dk → 5 dk → 15 dk → 1 sa. **Devre kesici:** 5 ardışık hata → `OPEN`; 15 dk sonra `HALF_OPEN`; başarı → `CLOSED`. Provider durumu `provider_state` tablosunda. Provider çökerse post `DATA_UNAVAILABLE` olur, silinmez.

**Uyarı durum makinesi (test saatiyle simüle edilebilir):**
`ACTIVE → W1 → W2 → W3 → FLAGGED(+yönetici eskalasyonu)`; yeni geçerli post → `ACTIVE`, `current_warning_count=0`, `flagged_at=NULL`, **geçmiş `warning_events` silinmez**. `unique(user_id, cycle_key, warning_number)` ile aynı uyarı iki kez sayılmaz; FLAGGED yalnızca 3. uyarı **teslim edilince** (prompt §35) set edilir.

---

## G. Provider Yetenek Matrisi

Resmî API şartları ve ücret/erişim kademeleri sık değişir; **uygulama sırasında güncel dokümandan doğrulanacak**. "Orbit'te var" sütunu okunan koda dayalıdır.

| Platform | Metrics | Comments | Views | Shares | Auth | Fallback | Orbit'te |
|---|---|---|---|---|---|---|---|
| YouTube | Evet (beğeni, yorum) | Evet (commentThreads) | Evet | Hayır (API sunmaz) | API anahtarı (herkese açık video) | Manuel | **Var** (video) |
| Threads | Evet | Yanıt metni bu bağlayıcıda yok | Evet | Evet (paylaşım/alıntı ayrı) | Kullanıcı OAuth, `threads_basic`+`threads_manage_insights`; yalnız **kendi** gönderisi | Manuel | **Var** |
| Instagram | Evet (yalnız yetkili profesyonel hesap) | Evet | Kısmen (insights) | Kısmen | Meta OAuth, işletme/creator; **kişisel hesap yok** | Manuel, oEmbed (metrik yok) | **Var** (son 50) |
| Facebook | Yalnız yönettiğin **Sayfa** | Sayfa gönderisi | Kısmen | Kısmen | Meta OAuth + sayfa izni; **kişisel profil/grup yok** | **Manuel** | **Var** (Sayfa) |
| X | Evet ama erişim kademeye/ücrete bağlı | Evet (kademeye bağlı) | Kademeye bağlı | Repost/quote | OAuth2 | Manuel | Yok |
| Reddit | Skor, yorum sayısı | Evet | **Yok** | Yok | OAuth, kullanım şartları/ticari kısıtlar | Manuel, RSS | Yok |
| Steam topluluğu | **Resmî post API'si yok** | — | — | — | — | Manuel / izin verilen public HTML | Yok |
| Discourse | Evet (`/t/{id}.json`: görüntülenme, beğeni, yanıt) | Evet | Evet | — | Genelde public | RSS | Yok |
| Genel forum | Siteye göre | Siteye göre | Bazen | — | Yok | **Manuel**, RSS | Yok |

**Sonuç:** "Her bağlantının etkileşimi" mutlaka kısmi olacak. Kapsam: YouTube, Threads, yetkili IG/FB Sayfası, Discourse, (ek erişimle) Reddit/X. Geri kalan manuel girilir ve **"manuel" etiketiyle** gösterilir; ölçülemeyen = "bilinmiyor", 0 değil.

---

## H. Güvenlik Tehdit Modeli

| Alan | Tehdit | Mevcut | Eklenecek |
|---|---|---|---|
| **Authentication** | Kaba kuvvet, oturum çalma | Supabase Auth, e-posta doğrulama, şifre değişiminde mevcut şifre kontrolü | Argon2id (Supabase Auth bcrypt kullanır: karşılaştırma notu), refresh rotasyonu/iptal Supabase'te; oturum açma hız sınırı |
| **Authorization** | Yatay/dikey yetki aşımı (USER başkasının postu, admin ucu) | RLS + `orbit_role()` DB'den | 5 rol, `organization_id` RLS, **RLS test paketi** (her rol × tablo), service_role yalnızca worker |
| **SSRF** | Post URL'si ile iç ağ/metadata erişimi | URL `^https?://` ve 2048 sınır | `lib/ssrf`: şema allowlist, localhost/özel IP/link-local (10/8, 172.16/12, 192.168/16, 127/8, ::1, 169.254/16) engeli, **DNS çözümlemesi sonrası IP kontrolü ve her redirect sonrası tekrar**, yanıt boyutu/süre limiti |
| **XSS** | Yorum/başlık/topluluk adı ile script | (düz JS'te doğrulanmadı) | Her metin `textContent`/escape; CSP; yorum metni render öncesi temizlenir |
| **Secrets** | Anahtar sızıntısı | Secret adıyla Edge Secret, Vault; `.env` yalnızca public anon bilgisi | Repo secret taraması, log redaksiyonu, sohbetlere/ekran görüntüsüne secret koymama |
| **OAuth tokens** | Çalınan/süresi dolan Meta/Threads token | Token Secret'ta, `owner_ids` yetkilendirmesi | Süre takibi + uyarı, **token'ı DB'ye düz yazmama**, yeniden yetkilendirme akışı, `AUTHORIZATION_REQUIRED` durumu |
| **Provider abuse** | Kotayı/ToS'u aşma, hesap kapatılması | Hesap başı 5, son 50 gönderi, ≤25 yorum | Provider başına rate state, devre kesici, minimum aralık, ölçüm yalnız yetkili hesap |
| **Rate limits** | API'yi boğma, 429 döngüsü | Worker deneme sayacı | Üstel geri çekilme, `Retry-After`, kullanıcı/IP limiti (RPC'ler) |
| **PII** | Yorum yazarı, kişi adları/e-posta | Bildirim hata ayrıntısında secret yok | Yazar SHA-256 pseudonym, yorum metni retention (180g), audit 365g, minimum veri, dışa aktarımda rol kontrolü |
| **Bildirim kötüye kullanımı** | Toplu spam, yanlış kişiye gönderim | Varsayılan kapalı, no-backfill, kişi hedef kontrolü | Kanal bazlı hız sınırı, `dedupe_key`, audit |
| **Audit** | İz bırakmama | Yok | `audit_logs` (actor, old/new, ip, ua) kritik işlemlerde |

---

## I. Geliştirme Fazları (bağımlılık sırası)

Her faz sonunda: format → lint → typecheck → test. Hata varken sonraki faza geçilmez.

**Faz 0 — Önkoşullar (kod yok):** Excel'in yeniden sağlanması; `Documents/ChatGPT/marketing` reposunun incelenmesi (git log, test durumu, masaüstü kopyalarla diff); kullanıcı kararları (aşağıda); Orbit'in bulut kurulum durumu (4 migration + worker + cron uygulandı mı) doğrulanması.
**Faz 1 — Temel:** repo+CI, `organizations/teams/games/campaigns`, `organization_id` backfill, 5 rol, `audit_logs`, RLS test paketi. *Kabul:* mevcut Orbit akışı kırılmadan çalışır; USER admin ucuna erişemez.
**Faz 2 — Post takip:** platform enum + URL tanıma, SSRF koruması, `PlatformProvider` arayüzü, `post_metric_snapshots`, adaptif zamanlama, idempotency key, mock mod ("MOCK DATA" rozeti). *Kabul:* link ekle → snapshot kaydı → tarihsel grafik.
**Faz 3 — Yorum ve sentiment:** `comments`, pseudonymize, Intelligence servisi, `comment_sentiments`, post detay ekranı. *Kabul:* Pozitif/Nötr/Negatif yüzdeleri.
**Faz 4 — Bildirim ve eskalasyon:** `warning_events`, kanal modeli, in-app realtime, test saati, FLAGGED, yönetici eskalasyonu. *Kabul:* test saatiyle 3 uyarı simülasyonu.
**Faz 5 — Community Radar:** `community_post_history`, `posting-context`, bileşenli skor + gerekçe metni.
**Faz 6 — Analitik:** performans motoru, normalize skor, liderlik tablosu, kampanya/topluluk/platform analitiği, özet tabloları, export.
**Faz 7 — Sertleştirme:** circuit breaker, health/metrics, yedekleme dokümanı, güvenlik taraması, E2E, kurulum paketi.

### Onayına sunulan kararlar (cevabına göre plan değişir)

1. **Yaklaşım:** Orbit'i evrimleştir + yalnız NLP için Python servisi (öneri) **mi**, yoksa master prompt'taki gibi sıfırdan FastAPI/Tauri **mi**?
2. **Excel:** `Başlıksız e-tablo.xlsx` dosyasını yeniden verir misin? (Etkileşim istatistiği ancak o zaman çıkarılır.)
3. **Çalışma konumu:** Kaynak `Documents/ChatGPT/marketing` (git'li). Geliştirmeyi orada mı yapalım, yoksa `Etkileşim takip` altında yeni bir repo mu?
4. **Hatırlatma:** `inactivity_days` 3 mü 7 mi; uyarılar aynı gün 3 slot mu, 24 saat arayla mı?
5. **Ölçek:** Tek ekip mi (Orbit'in 2 rolü yeter), yoksa çok şirketli SaaS mı?
6. **API erişimi:** Elinde Meta işletme hesabı, YouTube anahtarı, X API erişimi var mı? (Matris G buna göre daralır.)

---

## ADR-013 — Uygulanan karar (2026-10-05): yerel masaüstü, API'siz ölçüm

**Kullanıcı kararları:** Orbit temelli ilerle; `Etkileşim takip` reposu; hatırlatma ayarlarını yönetici
belirler; çok ekipli; API erişimi yok; ikinci prompt'taki yığın (Tauri v2 + React 18 + Python +
SQLite WAL + Telegram).

**Karar:** Yerel masaüstü uygulaması. Bu belgenin ADR-001/002/006 önerileri (Supabase evrimi) bu
sürüm için geçersizdir; Orbit/Supabase ile çok makineli senkron sonraki faza bırakıldı.

| Konu | Uygulama |
|---|---|
| Veri | SQLite WAL, `PRAGMA user_version` ile şema sürümü; metrikler zaman serisi |
| Çok ekip | `teams` + `users.team_id`; kurallar genel + ekip bazlı geçersiz kılma |
| Uyarı | 00:00 kontrol, eşik/aralık/uyarı sayısı ayarlı, son uyarıda `flagged` + yönetici/ekip Telegram |
| Bildirim | Outbox (`dedupe_key`), varsayılan kapalı, açılmadan önce birikenler toplu gitmez |
| Ölçüm | Herkese açık JSON → JSON-LD/OG → kullanıcının kendi tarayıcı oturumu → elle giriş |
| Duygu | Yerel TR/EN sözlük motoru (varsayılan); transformer yalnızca model yerelde varsa |
| Yetki | Yönetici PIN'i (scrypt, kilitlenme); PIN yalnızca ortam değişkeniyle motora |

**Reddedilen istek — anti-bot atlatma:** İkinci prompt `playwright-stealth`, bot korumasını atlatma
ve `cookies.json` taşıma istiyordu. Uygulanmadı: platform kullanım koşullarını ihlal eder, hesap
kapatılma riski taşır ve ilk master prompt'un "platform korumalarını bypass etme" kuralıyla çelişir.
Yerine: kullanıcının kendi oturumuyla gerçek Edge/Chrome profili (kalıcı profil, sır dosyası yok),
giriş duvarında `AUTHORIZATION_REQUIRED`, CAPTCHA/429'da `DATA_UNAVAILABLE` + platform duraklatma,
ölçülemeyenler için elle giriş. Nazik bekleme (2–5 sn) ve ölçülü kaydırma yalnızca sayfayı yüklemek
içindir, tespitten kaçmak için değil.

**Açık kalanlar:** Excel (`Başlıksız e-tablo.xlsx`) hâlâ yok → "Bağlantı" sütunu toplu içe aktarma
yapılmadı. Ayrıştırıcılar gerçek hesaplarla, Telegram teslimatı gerçek botla, NSIS paketleme bu
makinede doğrulanmadı.
