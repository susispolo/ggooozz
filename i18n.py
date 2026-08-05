"""Lightweight i18n for Music Suggest Bot.

Users pick a language (stored in user_prefs.db via bot.py). Text and keyboard
labels are looked up here by key, with English as the fallback default.
Persian (fa) is RTL so replies keep markdown/html but the flag/emoji labels
stay short.

Pattern: every user-facing string lives in TRANSLATIONS under a key; bot.py
calls `_{lang, "key", **fmt}` (or the shortcut `_t(user_lang, "key")`).
"""
import json
import os

_LANGS = {"en": "🇬🇧 English", "fa": "🇮🇷 فارسی"}


def supported_langs() -> dict:
    return dict(_LANGS)


# ── Core menu / navigation labels (≤ ~22 chars, one emoji convention) ──
LABELS = {
    "search":      {"en": "🔍 Search",      "fa": "🔍 جستجو"},
    "add_playlist":{"en": "➕ Add to Playlist", "fa": "➕ افزودن به لیست"},
    "my_playlist": {"en": "📋 My Playlist", "fa": "📋 لیست من"},
    "for_me":      {"en": "🎯 For Me",      "fa": "🎯 برای من"},
    "trivia":      {"en": "🎮 Trivia",      "fa": "🎮 مسابقه"},
    "lyrics":      {"en": "🎤 Lyrics",      "fa": "🎤 متن آهنگ"},
    "done":        {"en": "✅ Done",         "fa": "✅ تمام"},
    "cancel":      {"en": "❌ Cancel",       "fa": "❌ لغو"},
    "main_menu":   {"en": "🔙 Main Menu",    "fa": "🏠 منوی اصلی"},
    "refresh":     {"en": "🔄 Fresh Batch", "fa": "🔄 دسته جدید"},
    "language":    {"en": "🌐 Language / زبان", "fa": "🌐 زبان"},
}

# ── Longer text messages ──
MESSAGES = {
    "start_hero": {
        "en": ("🎵 <b>Music Suggest Bot</b>\n"
               "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
               "🎧 Find music you'll love!\n\n"
               "Send a song name or tap a button below to begin."),
        "fa": ("🎵 <b>ربات پیشنهاد موسیقی</b>\n"
               "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
               "🎧 موسیقی دلخواه‌تان را پیدا کنید!\n\n"
               "نام آهنگ را بفرستید یا از دکمه‌های پایین استفاده کنید."),
    },
    "for_me_header": {
        "en": ("🎯 <b>Songs Based on Your Taste</b>\n\n"
               "Based on {count} songs in your playlist:\n"
               "🥁 Avg BPM: {bpm} · ⚡ Energy: {energy}\n\n"
               "👆 <b>Click a song name to copy it</b> 👇"),
        "fa": ("🎯 <b>آهنگ‌های بر اساس سلیقه شما</b>\n\n"
               "بر اساس {count} آهنگ در لیست شما:\n"
               "🥁 میانگین BPM: {bpm} · ⚡ انرژی: {energy}\n\n"
               "👆 <b>برای کپی، روی نام آهنگ بزنید</b> 👇"),
    },
    "for_me_footer": {
        "en": ("━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
               "📝 <b>Paste the name in @DeezerMusicBot</b> to listen or download it.\n"
               "<i>Each has a 30-sec preview below 🎧</i>"),
        "fa": ("━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
               "📝 <b>نام را در @DeezerMusicBot جای‌گذاری کنید</b> تا پخش یا دانلود شود.\n"
               "<i>هرکدام پیش‌نمایش ۳۰ ثانیه‌ای دارند 🎧</i>"),
    },
    "for_me_locked": {
        "en": ("⏳ <b>Almost there!</b>\n\n"
               "You have <b>{count}</b> songs in your playlist.\n"
               "Add <b>{remaining} more</b> (10 total) to unlock <b>🎯 For Me</b>!\n\n"
               "Every song you add gives us 5 similar tracks to pick from."),
        "fa": ("⏳ <b>کمی مانده!</b>\n\n"
               "شما <b>{count}</b> آهنگ در لیست دارید.\n"
               "<b>{remaining} آهنگ دیگر</b> (مجموعاً ۱۰) اضافه کنید تا <b>🎯 برای من</b> فعال شود!\n\n"
               "هر آهنگ ۵ آهنگ مشابه به ما می‌دهد."),
    },
    "for_me_empty": {
        "en": "❌ No playlist data yet!\n\nTap <b>➕ Add to Playlist</b> to add songs first.",
        "fa": "❌ هنوز لیستی نیست!\n\nابتدا <b>➕ افزودن به لیست</b> را بزنید.",
    },
    "for_me_no_pool": {
        "en": "❌ No recommendations available yet.\n\nAdd more songs to your playlist!",
        "fa": "❌ هنوز پیشنهادی موجود نیست.\n\nآهنگ‌های بیشتری به لیست اضافه کنید!",
    },
    "for_me_fetch_fail": {
        "en": "❌ Couldn't fetch recommendations. Try again later.",
        "fa": "❌ دریافت پیشنهادها ناموفق بود. بعداً دوباره تلاش کنید.",
    },
    "for_me_error": {
        "en": "❌ Error finding recommendations. Try again.",
        "fa": "❌ خطا در یافتن پیشنهادها. دوباره تلاش کنید.",
    },
}

# module-level current language cache (per user_id) injected by bot.py
_user_lang = {}


def set_lang(user_id: int, code: str):
    _user_lang[user_id] = code if code in _LANGS else "en"


def get_lang(user_id: int) -> str:
    return _user_lang.get(user_id, "en")


def label(key: str, lang: str = "en") -> str:
    return LABELS.get(key, {}).get(lang) or LABELS.get(key, {}).get("en", key)


def msg(key: str, lang: str = "en", **fmt) -> str:
    t = MESSAGES.get(key, {}).get(lang) or MESSAGES.get(key, {}).get("en", key)
    if fmt:
        try:
            return t.format(**fmt)
        except (KeyError, IndexError):
            return t
    return t