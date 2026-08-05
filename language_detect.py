"""
Language detection for playlist songs.

Strategy (in priority order):
  1. Character-script detection (native scripts: Persian, Arabic, Cyrillic,
     Japanese, Korean, Thai, Chinese, etc.)
  2. Curated artist -> language map (catches transliterated names, e.g.
     "Fairuz" -> Arabic, K-pop/J-pop groups in Latin script, Persian artists
     written in English, etc.). Artist map OVERRIDES langdetect because
     langdetect is unreliable on short song titles (e.g. it guesses "tr"/"sw"
     for Fairuz's Arabic songs).
  3. langdetect fallback for titles in Latin script whose artist is unknown.
     Used only to fill in gaps (Spanish/Italian/French/German titles etc.)

Language codes: ISO 639-1 (en, fa, ar, ko, ja, ru, tr, es, fr, de, it, ...)
"""
import logging
import re

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════
# Curated artist -> language map
# ═══════════════════════════════════════════════════
# For artists whose name is in Latin script but who sing in a different
# language (transliterated Arabic/Persian/Korean/Japanese/etc).
# Add artists here as the user's playlist grows.
ARTIST_LANGUAGE_MAP = {
    # Arabic / Middle Eastern
    "fairuz": "ar",
    "fairouz": "ar",
    "fayrouz": "ar",
    "um kalthum": "ar",
    "om kalthoum": "ar",
    "amr diab": "ar",
    "nancy ajram": "ar",
    "elissa": "ar",
    "haifa wehbe": "ar",
    "kazem alsaher": "ar",
    "kadim al saher": "ar",
    "nawal al zoghbi": "ar",
    "sherine": "ar",
    "tamer hosny": "ar",
    "mohamed mounir": "ar",
    "cheb khaled": "ar",
    "rachid taha": "ar",
    "warda": "ar",
    "sabah": "ar",
    "abdul halim hafez": "ar",
    # Persian artists (often written in Latin script)
    "ebi": "fa",
    "googoosh": "fa",
    "dariush": "fa",
    "hayedeh": "fa",
    "shajarian": "fa",
    "mohsen namjoo": "fa",
    "mohsen chavoshi": "fa",
    "homayoun shajarian": "fa",
    "siavash ghomayshi": "fa",
    "siavash shams": "fa",
    "arash": "fa",
    "andy": "fa",
    "shahram shabpareh": "fa",
    "shohreh solati": "fa",
    "leila forouhar": "fa",
    "mansour": "fa",
    "sandy": "fa",
    "kaveh afagh": "fa",
    "reza bahram": "fa",
    "amir tataloo": "fa",
    "tataloo": "fa",
    "behnam bani": "fa",
    "moein": "fa",
    "sattar": "fa",
    "mahasti": "fa",
    "afshin": "fa",
    "soroush": "fa",
    "xaniar khosravi": "fa",
    "alireza ghorbani": "fa",
    "homayoun shajarian": "fa",
    "mohammadreza shajarian": "fa",
    "shahram nazeri": "fa",
    "mohsen yeganeh": "fa",
    "sina sarlak": "fa",
    "salar aghili": "fa",
    "mohammad motamedi": "fa",
    "pooran shokouhi": "fa",
    "homeyra": "fa",
    "shakila": "fa",
    "abbas ghadimi": "fa",
    "esfandiar ghorbani": "fa",
    # Turkish
    "tarkan": "tr",
    "sezen aksu": "tr",
    "baris manco": "tr",
    "ajda pekkan": "tr",
    "müslüm gürses": "tr",
    # Korean (K-pop / Korean artists, Latin script names)
    "bts": "ko",
    "blackpink": "ko",
    "exo": "ko",
    "twice": "ko",
    "red velvet": "ko",
    "nct": "ko",
    "stray kids": "ko",
    "itzy": "ko",
    "aespa": "ko",
    "enhypen": "ko",
    "seventeen": "ko",
    "gfriend": "ko",
    "mamamoo": "ko",
    "ikon": "ko",
    "winner": "ko",
    "big bang": "ko",
    "bigbang": "ko",
    "girls generation": "ko",
    "snsd": "ko",
    "shinee": "ko",
    "super junior": "ko",
    "2ne1": "ko",
    "psy": "ko",
    "iu": "ko",
    "taeyeon": "ko",
    "jennie": "ko",
    "lisa": "ko",
    "jisoo": "ko",
    "rosé": "ko",
    "jungkook": "ko",
    "v": "ko",
    "jimin": "ko",
    "suga": "ko",
    "rm": "ko",
    "j-hope": "ko",
    "txt": "ko",
    "le sserafim": "ko",
    "ive": "ko",
    "newjeans": "ko",
    # Japanese
    "utada hikaru": "ja",
    "hikaru utada": "ja",
    "radwimps": "ja",
    "radwimps": "ja",
    "kenshi yonezu": "ja",
    "yoasobi": "ja",
    "ado": "ja",
    "aimyon": "ja",
    "official hige dandism": "ja",
    "king gnu": "ja",
    "li sa": "ja",
    "yama": "ja",
    "zutomayo": "ja",
    # Chinese / Mandarin
    "jay chou": "zh",
    "周杰伦": "zh",
    "jj lin": "zh",
    "teresa teng": "zh",
    # Russian
    "tatu": "ru",
    "t.a.t.u.": "ru",
    "alla pugacheva": "ru",
    "dima bilan": "ru",
    # Spanish / Latin
    "luis fonsi": "es",
    "shakira": "es",
    "enrique iglesias": "es",
    "j balvin": "es",
    "bad bunny": "es",
    "maluma": "es",
    "rosalia": "es",
    "daddy yankee": "es",
    "juanes": "es",
    "ricky martin": "es",
    # French
    "stromae": "fr",
    "indila": "fr",
    "zaz": "fr",
    "johnny hallyday": "fr",
    "edith piaf": "fr",
    # Italian
    "andrea bocelli": "it",
    "eros ramazzotti": "it",
    "laura pausini": "it",
    "adriano celentano": "it",
    # German
    "rammstein": "de",
    "helene fischer": "de",
    "cro": "de",
    # Greek
    "mikis theodorakis": "el",
    "despina vandi": "el",
    # Hebrew
    "ofer levy": "he",
    "sarits hadad": "he",
    # Hindi / Bollywood
    "ar rahman": "hi",
    "a.r. rahman": "hi",
    "atif aslam": "hi",
    "kishore kumar": "hi",
    # Portuguese
    "michel telo": "pt",
    "anitta": "pt",
    "roberto carlos": "pt",
    # Armenian
    "system of a down": "hy",
    "harout pamboukjian": "hy",
}

# Language codes that are "localized" for a region but written in Latin
# script — keep these out of the generic langdetect fallback to avoid
# over-classification, but the artist map can still set them.

# ═══════════════════════════════════════════════════
# Script detection
# ═══════════════════════════════════════════════════
_FA_CHARS = set("پچژگک")
_AR_CHARS = set("ابتثجحخدذرزسشصضطظعغفقلمنهويءآأؤإةى")


def detect_script(text: str) -> str:
    """Detect language from Unicode character script. Returns ISO code or ''."""
    if not text:
        return ""
    for ch in text:
        code = ord(ch)
        if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F or 0xFB50 <= code <= 0xFDFF:
            # Arabic block. Persian adds پ چ ژ گ ک — distinguish Persian from Arabic
            if any(c in text for c in _FA_CHARS):
                return "fa"
            return "ar"
        if 0x0400 <= code <= 0x04FF:
            return "ru"
        if 0x3040 <= code <= 0x30FF or 0x4E00 <= code <= 0x9FFF:
            return "ja"
        if 0xAC00 <= code <= 0xD7AF:
            return "ko"
        if 0x0E00 <= code <= 0x0E7F:
            return "th"
        if 0x0590 <= code <= 0x05FF:
            return "he"
        if 0x0900 <= code <= 0x097F:
            return "hi"
        if 0x10A0 <= code <= 0x10FF:
            return "ka"
    return ""


def _normalize(name: str) -> str:
    """Normalize an artist name for map lookup."""
    return re.sub(r"[^a-z0-9\s]", "", name.lower()).strip()


def _lookup_artist_map(artist: str) -> str:
    """Check curated artist map. Returns language code or ''."""
    if not artist:
        return ""
    norm = _normalize(artist)
    if not norm:
        return ""
    # Try full normalized name, then progressively shorter prefixes
    # (handles "BTS - Dynamite" style, "Fairuz (feat. ...)" etc.)
    candidates = [norm]
    for sep in [" feat", " ft", " - ", "(", "[", ","]:
        if sep in norm:
            candidates.append(norm.split(sep)[0].strip())
    for cand in candidates:
        if cand in ARTIST_LANGUAGE_MAP:
            return ARTIST_LANGUAGE_MAP[cand]
    # Also try longest map key that is a word-boundary substring of the artist
    # name (handles "Fairuz (feat...)", "BTS & friends", etc.) but avoids
    # matching inside other words (e.g. "The Heavy" must NOT match "he").
    best = ""
    best_len = 0
    best_code = ""
    for key, code in ARTIST_LANGUAGE_MAP.items():
        if len(key) <= best_len:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", norm):
            best = key
            best_len = len(key)
            best_code = code
    if best:
        return best_code
    return ""


# Languages langdetect is trusted for on short title strings.
# It's notoriously wrong on Persian/Arabic/Turkish/Slavic (guesses like
# "sl"/"tr"/"cy"), so we only accept European-language guesses where it has
# real signal, and we also require the artist name to be UNKNOWN (not in map)
# and the text to be multi-word.
TRUSTED_LANGDETECT_LANGS = {
    "es", "fr", "de", "it", "pt", "nl", "sv", "no", "da", "fi", "pl", "cs", "hu", "ro", "id", "ms", "vi",
}


# Common English words that strongly indicate an English title (checked before
# langdetect so short English titles like "Freight Train" don't get tagged
# German/French etc. by the whitelist).
_ENGLISH_HINTS = {
    "the", "a", "an", "and", "of", "to", "in", "on", "for", "with", "my",
    "your", "love", "heart", "life", "time", "night", "day", "song", "man",
    "woman", "baby", "girl", "boy", "world", "fire", "rain", "train", "road",
    "home", "gone", "good", "bad", "never", "always", "stay", "take", "make",
    "feel", "know", "want", "need", "come", "get", "let", "like", "way",
    "one", "two", "you", "me", "we", "they", "it's", "don't", "can't", "wanna",
    "gonna", "oh", "yeah", "hey", "baby", "sweet", "little", "big", "old",
    "new", "black", "white", "red", "blue", "green", "gold", "high", "low",
    "long", "short", "back", "still", "just", "down", "up", "out", "there",
    "here", "every", "some", "any", "all", "more", "most", "other", "another",
    "what", "why", "when", "where", "who", "how", "if", "then", "than", "but",
    "so", "now", "then", "will", "would", "could", "should", "shall", "may",
    "might", "must", "have", "has", "had", "was", "were", "been", "being",
    "do", "does", "did", "am", "is", "are", "be",
    # more common song-title words
    "again", "alone", "away", "back", "before", "believe", "best", "better",
    "bring", "call", "change", "close", "come", "dance", "dream", "drive",
    "eyes", "fall", "feel", "find", "fire", "fly", "forget", "free", "friend",
    "give", "goodbye", "grow", "hand", "happy", "hard", "head", "hear",
    "hold", "hope", "hurt", "inside", "keep", "kind", "last", "leave",
    "leave", "left", "light", "listen", "live", "look", "lose", "lost",
    "mind", "miss", "morning", "move", "music", "name", "never", "night",
    "nothing", "now", "open", "part", "place", "play", "please", "pretty",
    "real", "remember", "right", "run", "save", "say", "see", "show",
    "sing", "sit", "sleep", "slow", "smile", "something", "song", "soon",
    "stand", "start", "stop", "story", "strong", "sun", "sunshine", "talk",
    "tell", "thing", "think", "tonight", "touch", "turn", "understand",
    "walk", "wait", "wake", "wonder", "work", "write", "year", "young",
    "remaster", "remastered", "version", "original", "album", "single",
    "edit", "live", "cover", "feat", "featuring", "deluxe", "bonus",
    "acoustic", "demo", "reissue", "anniversary", "mix", "remix",
}


def _has_english_hint(text: str) -> bool:
    """Check if text contains common English function/structure words."""
    if not text:
        return False
    words = set(re.findall(r"[a-z']+", text.lower()))
    return bool(words & _ENGLISH_HINTS)


def _langdetect_fallback(text: str) -> str:
    """Use langdetect as a conservative last resort.

    Only accepts a small whitelist of languages (European/Latin-script ones)
    where it's reasonably accurate. Never trusts its Slavic/ME/Arabic guesses
    ("sl", "tr", "cy", "az", etc.) — those are almost always wrong on song
    titles.
    """
    try:
        from langdetect import detect, DetectorFactory, LangDetectException
        DetectorFactory.seed = 0
        if not text or len(text) < 4:
            return ""
        lang = detect(text)
        if lang in TRUSTED_LANGDETECT_LANGS:
            return lang
        return ""
    except Exception:
        return ""


# Language display names + flag emoji
LANGUAGE_DISPLAY = {
    "en": ("English", "🇬🇧"),
    "fa": ("Persian", "🇮🇷"),
    "ar": ("Arabic", "🇱🇧"),
    "ko": ("Korean", "🇰🇷"),
    "ja": ("Japanese", "🇯🇵"),
    "zh": ("Chinese", "🇨🇳"),
    "ru": ("Russian", "🇷🇺"),
    "tr": ("Turkish", "🇹🇷"),
    "es": ("Spanish", "🇪🇸"),
    "fr": ("French", "🇫🇷"),
    "de": ("German", "🇩🇪"),
    "it": ("Italian", "🇮🇹"),
    "pt": ("Portuguese", "🇵🇹"),
    "el": ("Greek", "🇬🇷"),
    "he": ("Hebrew", "🇮🇱"),
    "hi": ("Hindi", "🇮🇳"),
    "th": ("Thai", "🇹🇭"),
    "ka": ("Georgian", "🇬🇪"),
    "hy": ("Armenian", "🇦🇲"),
    "uk": ("Ukrainian", "🇺🇦"),
    "nl": ("Dutch", "🇳🇱"),
    "pl": ("Polish", "🇵🇱"),
    "sv": ("Swedish", "🇸🇪"),
    "no": ("Norwegian", "🇳🇴"),
    "da": ("Danish", "🇩🇰"),
    "fi": ("Finnish", "🇫🇮"),
    "cs": ("Czech", "🇨🇿"),
    "hu": ("Hungarian", "🇭🇺"),
    "ro": ("Romanian", "🇷🇴"),
    "id": ("Indonesian", "🇮🇩"),
    "ms": ("Malay", "🇲🇾"),
    "vi": ("Vietnamese", "🇻🇳"),
    "ta": ("Tamil", "🇮🇳"),
    "te": ("Telugu", "🇮🇳"),
    "bn": ("Bengali", "🇧🇩"),
    "ur": ("Urdu", "🇵🇰"),
}


def detect_language(title: str, artist: str, original_text: str = "") -> str:
    """
    Detect the language of a song.
    Returns ISO 639-1 code (e.g. 'en', 'fa', 'ar', 'ko').

    Priority: script -> curated artist map -> langdetect fallback.
    """
    # 1. Script detection on original text (native scripts)
    for src in (original_text, title, artist):
        if src:
            script_lang = detect_script(src)
            if script_lang:
                return script_lang

    # 2. Curated artist map (overrides langdetect for known transliterated artists)
    map_lang = _lookup_artist_map(artist)
    if map_lang:
        return map_lang

    # 2a. Artist map also searched in the TITLE (covers "Fayrouz. Cover by ..."
    #     style entries where the artist name lives in the title field).
    if title:
        map_lang = _lookup_artist_map(title)
        if map_lang:
            return map_lang

    # 2b. English-word hint (before langdetect: short English titles like
    #     "Freight Train" must not be tagged German/French by the whitelist).
    if title and _has_english_hint(title):
        return "en"

    # 3. langdetect fallback on the title (Latin-script unknown artists)
    if title:
        return _langdetect_fallback(f"{title} {artist}".strip()) or "en"

    return "en"


def language_label(code: str) -> str:
    """Return (name, flag) for a language code."""
    name, flag = LANGUAGE_DISPLAY.get(code, (code, "🌐"))
    return name, flag
