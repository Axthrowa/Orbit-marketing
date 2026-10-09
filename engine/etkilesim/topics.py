"""Yorum konu analizi (master prompt §28): açıklanabilir TR/EN sözlük eşleşmesi, harici model yok.

Övgü konuları (oynanış, grafik) yalnızca olumlu/karışık yorumlarda, şikâyet konuları her yorumda
aranır. Bir yorum birden çok konuya girebilir. Yeni konu eklemek = TOPICS'e satır + test.
"""

from __future__ import annotations

import re

from .sentiment import tr_lower

TOPICS: dict[str, dict[str, object]] = {
    "bug": {
        "label": "Hata / bug şikâyeti",
        "praise": False,
        "pattern": r"\bbug|glitch|hata\b|hatalı|crash|çök|broken|bozuk|donuyor|donma",
    },
    "price": {
        "label": "Fiyat",
        "praise": False,
        "pattern": r"fiyat|pahalı|ucuz|\bprice|expensive|overpriced|cheap|indirim|discount|\$\d|\d+\s?tl\b",
    },
    "performance": {
        "label": "Performans / optimizasyon",
        "praise": False,
        "pattern": r"\blag|kasıyor|kasma|optimiz|performans|performance|stutter|fps düş|fps drop|takılıyor",
    },
    "server": {
        "label": "Sunucu / bağlantı",
        "praise": False,
        "pattern": r"sunucu|server|\bping\b|bağlantı kop|disconnect|matchmaking|eşleştirme",
    },
    "gameplay_praise": {
        "label": "Oynanış övgüsü",
        "praise": True,
        "pattern": r"oynanış|gameplay|mekanik|mechanic|eğlenceli|\bfun\b|bağımlılık|addictive",
    },
    "graphics_praise": {
        "label": "Grafik övgüsü",
        "praise": True,
        "pattern": r"grafik|görsel|graphics|visual|art style|sanat tarzı|atmosfer|atmosphere",
    },
    "feature_request": {
        "label": "Özellik isteği",
        "praise": False,
        "pattern": r"keşke|eklenmeli|ekleyin|eklerseniz|please add|would be (nice|great)|i wish|feature request|öneri",
    },
    "release_question": {
        "label": "Çıkış / erişim sorusu",
        "praise": False,
        "pattern": r"ne zaman|çıkış tarihi|release date|when (is|will)|beta|erken erişim|early access|wishlist",
    },
}
_COMPILED = {key: re.compile(str(spec["pattern"]), re.IGNORECASE) for key, spec in TOPICS.items()}
_PRAISE_LABELS = {"POSITIVE", "MIXED"}


def detect(text: str, label: str) -> list[str]:
    lowered = tr_lower(text)
    found: list[str] = []
    for key, pattern in _COMPILED.items():
        if TOPICS[key]["praise"] and label not in _PRAISE_LABELS:
            continue
        if pattern.search(lowered):
            found.append(key)
    return found


def labels() -> dict[str, str]:
    return {key: str(spec["label"]) for key, spec in TOPICS.items()}
