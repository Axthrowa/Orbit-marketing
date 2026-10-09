"""Yerel duygu analizi (Türkçe + İngilizce). Harici API yok, model indirmesi yok.

Hat: normalize → dil tespiti → spam filtresi → skor → kalibrasyon.
Emoji silinmez; duygu taşıyan emojiler skora katılır. @etiket ve URL maskelenir.
İsteğe bağlı `TransformerEngine` yalnızca model yerelde önbellekteyse çalışır.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Label = Literal["POSITIVE", "NEUTRAL", "NEGATIVE", "MIXED", "UNKNOWN"]

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MENTION_RE = re.compile(r"@\w+")
_TOKEN_RE = re.compile(r"[\w']+|[^\w\s]", re.UNICODE)
_REPEAT_RE = re.compile(r"(.)\1{2,}")

_TR_CHARS = set("ğüşıöçĞÜŞİÖÇ")
_TR_WORDS = {
    "ve",
    "bir",
    "bu",
    "çok",
    "ama",
    "için",
    "ben",
    "sen",
    "çünkü",
    "gibi",
    "daha",
    "değil",
    "oyun",
    "bence",
    "yok",
    "var",
    "ne",
    "mi",
    "mı",
    "da",
    "de",
}
_EN_WORDS = {
    "the",
    "and",
    "is",
    "this",
    "that",
    "game",
    "it",
    "to",
    "of",
    "for",
    "you",
    "not",
    "very",
    "so",
    "but",
    "with",
    "are",
    "was",
    "love",
    "like",
}

# Önek eşleşmesi ("*" ile biten) Türkçe çekimleri kapsar: güzel*, güzeldi, güzelmiş...
_LEXICON: dict[str, float] = {
    # Türkçe olumlu
    "güzel*": 2.0,
    "harika*": 2.5,
    "süper*": 2.2,
    "mükemmel*": 3.0,
    "efsane*": 2.8,
    "muhteşem*": 3.0,
    "bayıl*": 2.5,
    "beğen*": 2.0,
    "sev*": 2.0,
    "eğlenceli*": 2.0,
    "kaliteli*": 2.0,
    "başarılı*": 2.0,
    "tebrik*": 2.0,
    "teşekkür*": 1.5,
    "sağol*": 1.5,
    "eyvallah": 1.0,
    "bomba": 2.0,
    "iyi*": 1.5,
    "akıcı*": 1.5,
    "yakıyor": 2.0,
    "ateş": 1.5,
    "tavsiye": 1.0,
    "heyecan*": 1.5,
    "bekliyorum": 1.2,
    "merak*": 0.8,
    "oynanabilir*": 1.2,
    "bağımlı*": 1.5,
    "şahane": 2.5,
    "enfes": 2.5,
    "olmuş": 0.8,
    "tamam": 0.3,
    "sağlam*": 1.5,
    # Türkçe olumsuz
    "kötü*": -2.2,
    "berbat*": -3.0,
    "rezalet*": -3.0,
    "çöp": -2.8,
    "saçma*": -2.2,
    "sıkıcı*": -2.0,
    "bug*": -1.5,
    "hata*": -1.2,
    "donuyor": -2.0,
    "donma*": -2.0,
    "kasıyor": -2.0,
    "kasma*": -2.0,
    "lag*": -1.8,
    "pahalı*": -1.5,
    "rezil*": -2.8,
    "pişman*": -2.2,
    "iğrenç*": -3.0,
    "nefret*": -3.0,
    "kopya*": -1.8,
    "scam": -3.0,
    "dolandır*": -3.0,
    "hile*": -2.0,
    "p2w": -2.0,
    "çalıntı*": -2.0,
    "gereksiz*": -1.8,
    "başarısız*": -2.2,
    "fiyasko": -2.8,
    "sıkıldım": -2.0,
    "boşuna": -1.8,
    "kandır*": -2.5,
    "reklam": -0.8,
    "sorunlu": -1.5,
    "çökü*": -2.0,
    "çöküyor": -2.2,
    "vasat": -1.5,
    # İngilizce olumlu
    "good": 1.8,
    "great": 2.4,
    "awesome": 2.8,
    "amazing": 2.8,
    "love": 2.6,
    "loved": 2.6,
    "loving": 2.6,
    "nice": 1.6,
    "cool": 1.5,
    "fun": 1.8,
    "excellent": 2.8,
    "perfect": 2.8,
    "beautiful": 2.2,
    "best": 2.4,
    "wow": 1.8,
    "fantastic": 2.8,
    "impressive": 2.0,
    "congrats": 2.0,
    "congratulations": 2.0,
    "thanks": 1.2,
    "thank": 1.2,
    "smooth": 1.5,
    "polished": 1.8,
    "addictive": 1.5,
    "underrated": 1.5,
    "gem": 1.8,
    "banger": 2.2,
    "hyped": 1.8,
    "wishlisted": 1.8,
    "wishlist": 1.2,
    "recommend": 1.5,
    "worth": 1.2,
    # İngilizce olumsuz
    "bad": -2.0,
    "terrible": -3.0,
    "awful": -3.0,
    "trash": -2.8,
    "garbage": -2.8,
    "hate": -3.0,
    "hated": -3.0,
    "boring": -2.0,
    "buggy": -2.0,
    "broken": -2.2,
    "laggy": -2.0,
    "clone": -1.5,
    "waste": -2.2,
    "worst": -3.0,
    "ugly": -2.2,
    "stupid": -2.2,
    "spam": -2.0,
    "shill": -2.0,
    "refund": -2.0,
    "unplayable": -2.8,
    "disappointing": -2.2,
    "disappointed": -2.2,
    "mid": -1.0,
    "meh": -1.2,
    "cringe": -2.0,
    "ads": -0.8,
    "overpriced": -1.8,
    "crash": -1.8,
    "crashes": -1.8,
    "lazy": -1.5,
}
_PHRASES: dict[str, float] = {
    "can't wait": 2.5,
    "cant wait": 2.5,
    "take my money": 2.5,
    "pay to win": -2.5,
    "cash grab": -2.8,
    "dead game": -2.5,
    "no thanks": -1.5,
    "para tuzağı": -2.5,
    "pay2win": -2.5,
    "çok iyi": 0.5,
}
_EMOJI: dict[str, float] = {
    "❤": 2.0,
    "🔥": 1.5,
    "😍": 2.5,
    "🥰": 2.0,
    "👏": 1.5,
    "👍": 1.5,
    "😊": 1.5,
    "😎": 1.0,
    "💯": 1.5,
    "🙌": 1.5,
    "✨": 0.5,
    "😂": 0.4,
    "🤣": 0.4,
    "💪": 1.2,
    "🎉": 1.5,
    "💖": 2.0,
    "😡": -2.5,
    "🤬": -3.0,
    "👎": -2.0,
    "🤮": -3.0,
    "😠": -2.0,
    "😢": -1.0,
    "😭": -0.3,
    "💩": -2.5,
    "🙄": -1.5,
    "😒": -1.5,
    "🤡": -2.0,
    "🥱": -1.5,
    "😤": -1.5,
    "🗑": -2.0,
}
_NEGATORS_EN = {
    "not",
    "no",
    "never",
    "dont",
    "don't",
    "doesnt",
    "doesn't",
    "isnt",
    "isn't",
    "wasnt",
    "wasn't",
    "cant",
    "can't",
    "cannot",
    "wont",
    "won't",
    "didnt",
    "didn't",
    "aint",
    "ain't",
    "hardly",
    "without",
}
_INTENSIFIERS = {
    "çok",
    "aşırı",
    "gerçekten",
    "inanılmaz",
    "very",
    "really",
    "so",
    "super",
    "extremely",
    "absolutely",
    "fucking",
    "insanely",
}
_DIMINISHERS = {"biraz", "az", "kinda", "slightly", "bit", "somewhat", "pek"}
_TR_NEGATION_SUFFIX = re.compile(r"^(me|ma|mi|mı|mu|mü)")
_SPAM_RE = re.compile(
    r"follow me|check my (profile|page)|dm me|dm for|link in bio|sub4sub|f4f|l4l|free robux|"
    r"earn \$|t\.me/|telegram\.me|whatsapp|giveaway|çekiliş|takip et|takipleşelim|profilime bak|"
    r"kazanç|ek gelir|promo code",
    re.IGNORECASE,
)

MAX_STORED_LENGTH = 1000


@dataclass(frozen=True)
class SentimentResult:
    label: Label
    positive: float
    neutral: float
    negative: float
    language: str
    reason: str = ""


@dataclass(frozen=True)
class Ratios:
    positive: float
    neutral: float
    negative: float
    sample: int


class SentimentEngine(Protocol):
    name: str

    def analyze(self, texts: Sequence[str]) -> list[SentimentResult]: ...


class EngineUnavailable(Exception):
    pass


def tr_lower(text: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower()


def normalize(text: str) -> str:
    """URL ve @etiketleri maskeler, boşlukları toplar; emoji ve Türkçe karakterler korunur."""
    value = unicodedata.normalize("NFKC", text).replace("️", "").replace("’", "'")
    value = _URL_RE.sub(" ", value)
    value = _MENTION_RE.sub(" ", value)
    value = value.replace("#", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def mask_for_storage(text: str) -> str:
    """Saklanacak metin: URL atılır, @etiketler '@kullanıcı' olur (kişisel tanıtıcı tutulmaz)."""
    value = unicodedata.normalize("NFKC", text)
    value = _URL_RE.sub("[bağlantı]", value)
    value = _MENTION_RE.sub("@kullanıcı", value)
    return re.sub(r"\s+", " ", value).strip()[:MAX_STORED_LENGTH]


def text_hash(text: str) -> str:
    key = tr_lower(re.sub(r"\s+", " ", normalize(text)))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def detect_language(text: str) -> str:
    tokens = {t for t in re.findall(r"[\w']+", tr_lower(text))}
    tr_score = sum(1 for ch in text if ch in _TR_CHARS) + 2 * len(tokens & _TR_WORDS)
    en_score = 2 * len(tokens & _EN_WORDS)
    if tr_score == 0 and en_score == 0:
        return "und"
    return "tr" if tr_score >= en_score else "en"


_PREFIX_ENTRIES = [(key[:-1], value) for key, value in _LEXICON.items() if key.endswith("*")]
_TR_NEGATORS = {"değil", "degil"}
# Önek eşleşmesinin yanlış yakaladığı yaygın sözcükler ("bugün" ≠ bug, "seviye" ≠ sev).
_PREFIX_EXCLUDED = ("bugün", "seviye", "sevk", "hatay", "hatıra", "hatırl", "lagos", "ateşli")


def _stem_score(token: str) -> tuple[float, str | None] | None:
    """(skor, eşleşen önek) — tam eşleşme önce, sonra önek; önek yoksa None."""
    direct = _LEXICON.get(token)
    if direct is not None:
        return direct, None
    if token.startswith(_PREFIX_EXCLUDED):
        return None
    for stem, value in _PREFIX_ENTRIES:
        if token.startswith(stem):
            return value, stem
    return None


def _token_score(token: str) -> float | None:
    if token in _EMOJI:
        return _EMOJI[token]
    hit = _stem_score(token)
    if hit is None:
        return None
    score, stem = hit
    if stem is not None and _TR_NEGATION_SUFFIX.match(token[len(stem) :]):
        return -abs(score) * 0.9  # beğenmedim, sevmedim
    return score


def _score_tokens(tokens: list[str]) -> tuple[float, float]:
    scored: dict[int, float] = {}
    for index, token in enumerate(tokens):
        score = _token_score(token)
        if score is None:
            continue
        previous = tokens[index - 1] if index else ""
        if previous in _INTENSIFIERS:
            score *= 1.5
        elif previous in _DIMINISHERS:
            score *= 0.6
        if any(w in _NEGATORS_EN for w in tokens[max(0, index - 3) : index]):
            score *= -0.75
        scored[index] = score
    for index, token in enumerate(tokens):
        if token in _TR_NEGATORS:  # "güzel değil"
            for position in scored:
                if 0 < index - position <= 2:
                    scored[position] *= -0.75
    positive = sum(v for v in scored.values() if v > 0)
    negative = -sum(v for v in scored.values() if v < 0)
    return positive, negative


def analyze_text(text: str) -> SentimentResult:
    normalized = normalize(text)
    language = detect_language(normalized)
    if not any(ch.isalpha() or ch in _EMOJI for ch in normalized):
        return SentimentResult("UNKNOWN", 0.0, 1.0, 0.0, language, "boş/anlamsız")
    if _SPAM_RE.search(text) or len(_URL_RE.findall(text)) >= 2:
        return SentimentResult("UNKNOWN", 0.0, 1.0, 0.0, language, "spam")
    lowered = tr_lower(normalized)
    lowered = _REPEAT_RE.sub(r"\1\1", lowered)
    phrase_bonus_pos = 0.0
    phrase_bonus_neg = 0.0
    for phrase, value in _PHRASES.items():
        if phrase in lowered:
            lowered = lowered.replace(phrase, " ")
            if value > 0:
                phrase_bonus_pos += value
            else:
                phrase_bonus_neg += -value
    tokens = _TOKEN_RE.findall(lowered)
    positive, negative = _score_tokens(tokens)
    positive += phrase_bonus_pos
    negative += phrase_bonus_neg
    if "!" in text and (positive or negative):
        boost = 1.0 + min(text.count("!"), 3) * 0.1
        positive *= boost
        negative *= boost
    total = positive + negative + 1.5
    pos_p, neg_p, neu_p = positive / total, negative / total, 1.5 / total
    compound = (positive - negative) / math.sqrt((positive - negative) ** 2 + 15)
    big, small = max(positive, negative), min(positive, negative)
    if small >= 1.5 and small / big >= 0.4:
        label: Label = "MIXED"
    elif compound >= 0.2:
        label = "POSITIVE"
    elif compound <= -0.2:
        label = "NEGATIVE"
    else:
        label = "NEUTRAL"
    return SentimentResult(label, round(pos_p, 4), round(neu_p, 4), round(neg_p, 4), language)


class LexiconEngine:
    name = "lexicon-tr-en-v1"

    def analyze(self, texts: Sequence[str]) -> list[SentimentResult]:
        return [analyze_text(text) for text in texts]


class TransformerEngine:
    """cardiffnlp/twitter-xlm-roberta-base-sentiment; model yerelde yoksa indirmez."""

    MODEL = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
    name = "xlm-roberta-sentiment"

    def __init__(self) -> None:
        try:
            from transformers import pipeline  # type: ignore[import-not-found,unused-ignore]
        except ImportError as exc:
            raise EngineUnavailable("transformers kurulu değil") from exc
        try:
            self._pipe = pipeline(
                "text-classification", model=self.MODEL, top_k=None, model_kwargs={"local_files_only": True}
            )
        except Exception as exc:
            raise EngineUnavailable("Model yerelde bulunamadı (indirme yapılmaz)") from exc

    def analyze(self, texts: Sequence[str]) -> list[SentimentResult]:
        results: list[SentimentResult] = []
        for text in texts:
            base = analyze_text(text)
            if base.label == "UNKNOWN":
                results.append(base)
                continue
            scores = {
                item["label"].lower(): float(item["score"]) for item in self._pipe(normalize(text)[:512])[0]
            }
            pos = scores.get("positive", 0.0)
            neg = scores.get("negative", 0.0)
            neu = scores.get("neutral", 0.0)
            label: Label = max(
                (("POSITIVE", pos), ("NEGATIVE", neg), ("NEUTRAL", neu)), key=lambda pair: pair[1]
            )[0]  # type: ignore[assignment]
            results.append(SentimentResult(label, pos, neu, neg, base.language))
        return results


def get_engine(name: str) -> SentimentEngine:
    if name == "transformer":
        try:
            return TransformerEngine()
        except EngineUnavailable:
            return LexiconEngine()  # zarif geri dönüş: düşük güvenli kural tabanlı motor
    return LexiconEngine()


def aggregate_labels(labels: Sequence[str]) -> Ratios | None:
    """UNKNOWN (spam/boş) hariç oranlar. MIXED nötr sayılır. Örnek yoksa None."""
    usable = [label for label in labels if label != "UNKNOWN"]
    if not usable:
        return None
    count = len(usable)
    positive = usable.count("POSITIVE") / count
    negative = usable.count("NEGATIVE") / count
    return Ratios(round(positive, 4), round(1 - positive - negative, 4), round(negative, 4), count)


def aggregate(results: Sequence[SentimentResult]) -> Ratios | None:
    return aggregate_labels([r.label for r in results])
