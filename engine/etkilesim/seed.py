"""Geliştirme tohum verisi (master prompt §90): 2 ekip, 1 yönetici, 5 kişi, 3 oyun, 4 kampanya,
30 paylaşım, 20 topluluk, ölçüm geçmişi, yorumlar, uyarılar ve bildirimler.

Yalnızca BOŞ veritabanına uygulanır (gerçek veriyi kirletmez). Tüm ölçümler `MOCK` kaynaklıdır ve
arayüzde "MOCK DATA" olarak görünür. Bağlantılar örnek adreslerdir.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from . import catalog, mockprovider, people, posts, strikes
from .clock import now_utc, to_iso
from .db import audit
from .errors import ValidationFailed
from .sentiment import LexiconEngine

_TEAMS = (("Marketing A", "-1001112223334"), ("Marketing B", None))
_PEOPLE = (
    ("Yönetici", 0, "admin"),
    ("Ayşe Demir", 0, "manager"),
    ("Burak Yıldız", 0, "member"),
    ("Cem Kaya", 1, "manager"),
    ("Deniz Acar", 1, "member"),
    ("Elif Şahin", 1, "member"),
)
_GAMES: tuple[dict[str, Any], ...] = (
    {
        "name": "Project Nova",
        "genres": ["FPS", "Extraction Shooter"],
        "keywords": ["pvpve", "tactical"],
        "languages": ["en", "tr"],
    },
    {
        "name": "Skyforge Tales",
        "genres": ["RPG", "Açık dünya"],
        "keywords": ["fantasy", "crafting"],
        "languages": ["tr"],
    },
    {
        "name": "Pixel Racers",
        "genres": ["Yarış", "Arcade"],
        "keywords": ["racing", "retro"],
        "languages": ["en"],
    },
)
_CAMPAIGNS: tuple[tuple[str, int, str], ...] = (
    ("Nova Beta Duyurusu", 0, "active"),
    ("Nova Steam Next Fest", 0, "active"),
    ("Skyforge Kickstarter", 1, "active"),
    ("Pixel Racers Lansman", 2, "finished"),
)
_COMMUNITIES: tuple[tuple[str, str, int | None, str | None, str, float], ...] = (
    ("r/FPS", "Reddit", 1_200_000, "en", "FPS games and shooter news", 0.1),
    ("r/ExtractionShooter", "Reddit", 85_000, "en", "Extraction shooter community", 0.1),
    ("r/IndieGaming", "Reddit", 3_400_000, "en", "Indie games showcase", 0.2),
    ("r/indiegames", "Reddit", 900_000, "en", "Indie game developers and players", 0.2),
    ("r/RPG_Gamers", "Reddit", 210_000, "en", "RPG fantasy open world fans", 0.1),
    ("r/racinggames", "Reddit", 130_000, "en", "Racing games arcade and sim", 0.1),
    ("r/RetroGaming", "Reddit", 1_500_000, "en", "Retro arcade gaming", 0.1),
    ("r/TurkGamers", "Reddit", 40_000, "tr", "Türk oyuncular topluluğu", 0.1),
    ("r/oyunlar", "Reddit", 25_000, "tr", "Türkçe oyun sohbeti", 0.1),
    ("r/gamedev", "Reddit", 1_300_000, "en", "Game development discussion", 0.3),
    ("r/pcgaming", "Reddit", 4_000_000, "en", "PC gaming news", 0.2),
    ("r/FreeGameGiveaways", "Reddit", 60, "en", "free giveaway promo codes", 0.8),
    ("FPS Türkiye", "Facebook", None, "tr", "FPS oyuncuları grubu", 0.2),
    ("Oyuncular Grubu", "Facebook", None, "tr", "Genel oyun grubu", 0.3),
    ("Açık Dünya Severler", "Facebook", None, "tr", "RPG açık dünya oyunları", 0.2),
    ("Nova Discord Duyuru", "Other", 12_000, "en", "Project Nova official community", 0.0),
    ("Technopat Forum", "Forum", None, "tr", "Teknoloji ve oyun forumu", 0.1),
    ("DonanımHaber Oyun", "Forum", None, "tr", "Oyun tartışmaları", 0.1),
    ("ResetEra Indie", "Forum", None, "en", "Indie game discussion forum", 0.1),
    ("Steam Next Fest Hub", "Other", None, "en", "Steam festival demos", 0.2),
)
_PLATFORM_URLS = {
    "X": "https://x.com/{handle}/status/18{n:016d}",
    "Reddit": "https://www.reddit.com/r/demo/comments/{n:x}/demo_post/",
    "Instagram": "https://www.instagram.com/p/Demo{n}/",
    "YouTube": "https://www.youtube.com/watch?v=demo{n:07d}",
    "Threads": "https://www.threads.net/@{handle}/post/Demo{n}",
    "Facebook": "https://www.facebook.com/groups/demo/posts/{n}",
}
_NOTES = (
    "Moderatörler doğrudan Steam linkini siliyor; oynanış videosuyla paylaşınca daha çok yorum geldi.",
    "Cuma akşamları çok aktif, hafta içi sabah ilgi düşük.",
    "Kendi tanıtım günleri var (pazar); diğer günler kaldırılıyor.",
    None,
    None,
)


def _public(_host: str, _port: int) -> list[str]:
    return ["93.184.216.34"]  # örnek adresler için DNS'e gitmeden "genel ağ" kabulü


def seed_demo(conn: sqlite3.Connection, now: datetime | None = None, actor: str = "admin") -> dict[str, int]:
    moment = now or now_utc()
    if (
        conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        or conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    ):
        raise ValidationFailed("Tohum verisi yalnızca boş veritabanına eklenebilir")
    start = moment - timedelta(days=35)
    team_ids = [people.create_team(conn, name, chat, actor, start) for name, chat in _TEAMS]
    user_ids = []
    for index, (name, team, role) in enumerate(_PEOPLE):
        user_ids.append(
            people.create_user(
                conn,
                name,
                team_ids[team],
                role,
                f"10000000{index}",
                actor,
                start,
                email=f"kisi{index}@example.com",
            )
        )
    game_ids = [catalog.create_game(conn, dict(game), actor, start) for game in _GAMES]
    campaign_ids = [
        catalog.create_campaign(conn, {"name": name, "game_id": game_ids[g], "status": status}, actor, start)
        for name, g, status in _CAMPAIGNS
    ]
    for name, platform, members, lang, desc, spam in _COMMUNITIES:
        conn.execute(
            "INSERT INTO communities(name,name_key,platform,url,member_count,status,relevance_score,"
            "activity_score,"
            "reason,discovered_at,description,language,spam_risk,last_scanned_at) VALUES"
            " (?,?,?,?,?,'discovered',NULL,?,?,?,?,?,?,?)",
            (
                name,
                name.lower().removeprefix("r/"),
                platform,
                f"https://www.reddit.com/{name}/" if name.startswith("r/") else None,
                members,
                None if members is None else min(1.0, len(str(members)) / 7),
                "Tohum verisi",
                to_iso(start),
                desc,
                lang,
                spam,
                to_iso(moment),
            ),
        )
    engine = LexiconEngine()
    platforms = list(_PLATFORM_URLS)
    posters = user_ids[1:]  # yönetici paylaşım yapmaz
    created = 0
    for n in range(30):
        uid = posters[n % len(posters)]
        if uid == posters[1] and n > 6:  # Burak bir süredir paylaşım yapmıyor → uyarılar
            uid = posters[(n + 1) % len(posters)]
        platform = platforms[n % len(platforms)]
        posted = moment - timedelta(days=30 - n, hours=n % 7)
        community_name = _COMMUNITIES[(n * 3) % 15][0]
        url = _PLATFORM_URLS[platform].format(handle=f"demo{uid}", n=1000 + n)
        result = posts.add_post(
            conn,
            uid,
            url,
            community_name=community_name,
            preview_text=f"Örnek paylaşım #{n + 1}: yeni fragman ve demo duyurusu",
            note=_NOTES[n % len(_NOTES)],
            posted_at=to_iso(posted),
            actor=actor,
            now=posted,
            resolver=_public,
            campaign_id=campaign_ids[n % len(campaign_ids)] if n % 5 else None,
            content_type=("post", "video", "image", "event")[n % 4],
        )
        created += 1
        for hours in (2, 12, 48, 24 * 6):
            when = posted + timedelta(hours=hours)
            if when > moment:
                break
            sample = mockprovider.collect(result.post_id, platform, posted, when, 20)
            posts.record_collect(conn, result.post_id, sample, engine, when, 20)
    for day in (3, 2, 1, 0):  # test saatiyle geriye dönük gece kontrolleri → uyarılar + işaretleme
        strikes.run_inactivity_check(conn, moment - timedelta(days=day))
    conn.execute(
        "INSERT INTO settings(scope,key,value_json,updated_at) VALUES ('meta','demo_seeded',?,?)"
        " ON CONFLICT(scope,key) DO UPDATE SET value_json=excluded.value_json",
        (json.dumps(to_iso(moment)), to_iso(moment)),
    )
    counts = {
        "teams": len(team_ids),
        "users": len(user_ids),
        "games": len(game_ids),
        "campaigns": len(campaign_ids),
        "communities": len(_COMMUNITIES),
        "posts": created,
        "snapshots": int(conn.execute("SELECT COUNT(*) FROM post_metric_snapshots").fetchone()[0]),
        "comments": int(conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0]),
        "warnings": int(conn.execute("SELECT COUNT(*) FROM strike_events").fetchone()[0]),
        "notifications": int(conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]),
    }
    audit(conn, actor, "seed.demo", None, None, counts, moment)
    return counts
