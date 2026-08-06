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
    "search_again": {"en": "🔄 Search Again", "fa": "🔄 جستجوی دوباره"},
    "how_to_play": {"en": "🎧 How to play & download", "fa": "🎧 راهنمای پخش و دانلود"},
}

# ── Longer text messages ──
MESSAGES = {
    "start_hero": {
        "en": ("🎵 <b>Music Suggest Bot</b> 🎶\n"
               "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
               "👋 <b>Hi! I'm your personal music finder.</b>\n"
               "Send me any <b>song name</b> 🎤 or an <b>MP3/voice</b> 🎧 and I'll find it, "
               "show you its details (BPM, genre, energy…) and recommend <b>similar tracks</b> you'll love! 💜\n\n"
               "🕹️ <b>What the buttons do:</b>\n"
               "🔍 <b>Search</b> — type a song name, I'll find it + similar tracks\n"
               "➕ <b>Add to Playlist</b> — build your taste profile\n"
               "📋 <b>My Playlist</b> — see what you've added\n"
               "🎯 <b>For Me</b> — songs picked for YOUR taste (unlocks at 10 songs)\n"
               "🎮 <b>Trivia</b> — guess the song, fun game!\n"
               "🎤 <b>Lyrics</b> — get song lyrics\n\n"
               "⬇️ <b>Want to listen or download?</b>\n"
               "Tap <b>@DeezerMusicBot</b> button on any song result — paste the song name and download it. 🎧\n\n"
               "👉 Type a song name or tap a button below to start! 🚀"),
        "fa": ("🎵 <b>ربات پیشنهاد موسیقی</b> 🎶\n"
               "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
               "👋 <b>سلام! من دستیار شخصی موسیقی شما هستم.</b>\n"
               "هر <b>نام آهنگ</b> 🎤 یا <b>فایل صوتی/ویس</b> 🎧 بفرستید تا پیدایش کنم، "
               "جزئیاتش (BPM، سبک، انرژی و…) را نشان دهم و <b>آهنگ‌های مشابه</b> را پیشنهاد دهم! 💜\n\n"
               "🕹️ <b>دکمه‌ها چه کاری انجام می‌دهند:</b>\n"
               "🔍 <b>جستجو</b> — نام آهنگ را بفرستید، پیدا می‌کنم + آهنگ‌های مشابه\n"
               "➕ <b>افزودن به لیست</b> — بسازید سلیقه‌تان را بشناسد\n"
               "📋 <b>لیست من</b> — ببینید چه افزوده‌اید\n"
               "🎯 <b>برای من</b> — آهنگ‌های مخصوص سلیقه شما (با ۱۰ آهنگ فعال می‌شود)\n"
               "🎮 <b>مسابقه</b> — حدس بزنید آهنگ چیست!\n"
               "🎤 <b>متن آهنگ</b> — متن آهنگ‌ها را بگیرید\n\n"
               "⬇️ <b>می‌خواهید گوش دهید یا دانلود کنید؟</b>\n"
               "روی دکمه <b>@DeezerMusicBot</b> زیر هر نتیجه بزنید — نام آهنگ را جای‌گذاری کنید و دانلود کنید. 🎧\n\n"
               "👉 نام یک آهنگ را بفرستید یا روی یکی از دکمه‌های زیر بزنید! 🚀"),
    },
    "help_text": {
        "en": ("🎵 <b>Music Suggest Bot</b> 🎶\n"
               "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
               "🤖 <b>What I do:</b> find songs by name, recognize MP3/voice files, "
               "show BPM/genre/energy, recommend similar tracks, and learn your taste to pick songs for you.\n\n"
               "🕹️ <b>Menu buttons:</b>\n"
               "🔍 <b>Search</b> — type a song name, pick the right one, get similar tracks\n"
               "➕ <b>Add to Playlist</b> — add songs (type names or send audio); tap <b>✅ Done</b> when finished\n"
               "📋 <b>My Playlist</b> — view your songs + taste stats\n"
               "🎯 <b>For Me</b> — 5 fresh songs matched to your taste (needs 10+ songs)\n"
               "🎮 <b>Trivia</b> — guess the song from its preview\n"
               "🎤 <b>Lyrics</b> — send <i>song artist</i> to get lyrics\n\n"
               "🎧 <b>How to download a song:</b>\n"
               "Tap the <b>⬇️ @DeezerMusicBot</b> button on any result, paste the song name there, and download. Simple! 😉\n\n"
               "📌 Tip: tap any <code>song - artist</code> text to copy it.\n"
               "🌐 Switch language anytime with <b>/language</b>."),
        "fa": ("🎵 <b>ربات پیشنهاد موسیقی</b> 🎶\n"
               "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
               "🤖 <b>چه کاری انجام می‌دهم:</b> پیدا کردن آهنگ با نام، تشخیص فایل صوتی/ویس، "
               "نمایش BPM/سبک/انرژی، پیشنهاد آهنگ‌های مشابه، و شناخت سلیقه شما برای انتخاب آهنگ.\n\n"
               "🕹️ <b>دکمه‌های منو:</b>\n"
               "🔍 <b>جستجو</b> — نام آهنگ را بفرستید، مورد درست را انتخاب کنید، آهنگ‌های مشابه بگیرید\n"
               "➕ <b>افزودن به لیست</b> — آهنگ اضافه کنید (نام بفرستید یا فایل صوتی)؛ در پایان <b>✅ تمام</b> را بزنید\n"
               "📋 <b>لیست من</b> — آهنگ‌ها و آمار سلیقه‌تان\n"
               "🎯 <b>برای من</b> — ۵ آهنگ تازه متناسب با سلیقه شما (به ۱۰+ آهنگ نیاز دارد)\n"
               "🎮 <b>مسابقه</b> — آهنگ را از پیش‌نمایش حدس بزنید\n"
               "🎤 <b>متن آهنگ</b> — <i>نام آهنگ و خواننده</i> را بفرستید تا متن بگیرید\n\n"
               "🎧 <b>چطور آهنگ را دانلود کنیم:</b>\n"
               "روی دکمه <b>⬇️ @DeezerMusicBot</b> زیر هر نتیجه بزنید، نام آهنگ را آنجا جای‌گذاری کنید و دانلود کنید. ساده! 😉\n\n"
               "📌 نکته: روی هر متن <code>آهنگ - خواننده</code> بزنید تا کپی شود.\n"
               "🌐 هر وقت خواستید با <b>/language</b> زبان را عوض کنید."),
    },
    "search_prompt": {
        "en": "🔍 <b>Type a song name to search</b> 🎵\ne.g. <i>Bohemian Rhapsody</i> or <i>Shape of You</i>\n\nI'll find it, show its details, and recommend similar tracks!",
        "fa": "🔍 <b>نام یک آهنگ را برای جستجو بفرستید</b> 🎵\nمثلاً <i>بوهمین راپسودی</i> یا <i>شِیپ آو یو</i>\n\nآن را پیدا می‌کنم، جزئیاتش را نشان می‌دهم و آهنگ‌های مشابه را پیشنهاد می‌کنم!",
    },
    "copy_hint": {
        "en": "⬆️ <i>Tap to copy</i>",
        "fa": "⬆️ <i>برای کپی بزنید</i>",
    },
    "selected_track_header": {
        "en": "━━━ <b>Selected Track</b> ━━━",
        "fa": "━━━ <b>آهنگ انتخاب‌شده</b> ━━━",
    },
    "similar_tracks_header": {
        "en": "🎯 <b>Similar Tracks</b>",
        "fa": "🎯 <b>آهنگ‌های مشابه</b>",
    },
    "download_cta": {
        "en": "🎧 <b>Want to listen or download this?</b>\nTap the <b>⬇️ @DeezerMusicBot</b> button below 🔽\n\nPaste the song name there and download it for free! 💾",
        "fa": "🎧 <b>می‌خواهید این را گوش دهید یا دانلود کنید؟</b>\nروی دکمه <b>⬇️ @DeezerMusicBot</b> زیر 🔽 بزنید\n\nنام آهنگ را آنجا جای‌گذاری کنید و رایگان دانلود کنید! 💾",
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
               "⬇️ <b>Want to play or download?</b>\n"
               "Tap the <b>@DeezerMusicBot</b> button below 👇\n"
               "<i>(Each song has a 30-sec preview above 🎧)</i>"),
        "fa": ("━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
               "⬇️ <b>می‌خواهید پخش یا دانلود کنید؟</b>\n"
               "روی دکمه <b>@DeezerMusicBot</b> زیر 👇 بزنید\n"
               "<i>(هر آهنگ پیش‌نمایش ۳۰ ثانیه‌ای دارد 🎧)</i>"),
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
    # Preserve '' (first-time user, not yet chosen) so /start can detect it;
    # any other unknown code falls back to English.
    if code == "":
        _user_lang[user_id] = ""
    else:
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