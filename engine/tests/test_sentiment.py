from __future__ import annotations

import pytest

from etkilesim import sentiment as s


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("Bu oyun gerçekten harika, bayıldım!", "POSITIVE"),
        ("This game is awesome, love it", "POSITIVE"),
        ("Berbat bir oyun, tam çöp", "NEGATIVE"),
        ("Absolutely terrible, total garbage", "NEGATIVE"),
        ("Beğenmedim, hiç sevmedim", "NEGATIVE"),
        ("not good at all", "NEGATIVE"),
        ("güzel değil", "NEGATIVE"),
        ("Bugün yeni bir seviye ekledik", "NEUTRAL"),
        ("🔥🔥❤️", "POSITIVE"),
        ("😡🤬", "NEGATIVE"),
        ("Grafikler harika ama oyun çok kasıyor ve bug dolu", "MIXED"),
        ("Fiyatı ne kadar?", "NEUTRAL"),
    ],
)
def test_labels(text: str, label: str) -> None:
    assert s.analyze_text(text).label == label


def test_probabilities_sum_to_one() -> None:
    r = s.analyze_text("harika oyun")
    assert abs(r.positive + r.neutral + r.negative - 1.0) < 0.01


def test_spam_and_empty_are_unknown() -> None:
    assert s.analyze_text("Follow me for free robux").label == "UNKNOWN"
    assert s.analyze_text("https://example.com/x").label == "UNKNOWN"
    assert s.analyze_text("@someone").label == "UNKNOWN"


def test_turkish_dotted_i_lowering() -> None:
    assert s.tr_lower("IŞIK İYİ") == "ışık iyi"


def test_language_detection() -> None:
    assert s.detect_language("çok güzel bir oyun ama bence pahalı") == "tr"
    assert s.detect_language("this is a very good game and i love it") == "en"
    assert s.detect_language("12345") == "und"


def test_storage_masking_removes_mentions_and_urls() -> None:
    masked = s.mask_for_storage("@ahmet bak https://x.com/a/status/1 süper")
    assert "ahmet" not in masked
    assert "http" not in masked
    assert "@kullanıcı" in masked


def test_hash_ignores_case_whitespace_and_urls() -> None:
    assert s.text_hash("Süper  OYUN https://a.co") == s.text_hash("süper oyun")


def test_aggregate_excludes_unknown_and_counts_mixed_as_neutral() -> None:
    results = s.LexiconEngine().analyze(
        ["harika", "berbat", "fiyatı ne", "follow me for free robux", "süper"]
    )
    ratios = s.aggregate(results)
    assert ratios is not None
    assert ratios.sample == 4
    assert ratios.positive == 0.5
    assert ratios.negative == 0.25
    assert abs(ratios.positive + ratios.neutral + ratios.negative - 1.0) < 0.001


def test_aggregate_none_when_no_usable_samples() -> None:
    assert s.aggregate([]) is None
    assert s.aggregate(s.LexiconEngine().analyze(["follow me", "@a"])) is None


def test_get_engine_falls_back_without_transformers() -> None:
    assert s.get_engine("transformer").name in {s.LexiconEngine.name, s.TransformerEngine.name}
    assert s.get_engine("lexicon").name == s.LexiconEngine.name
