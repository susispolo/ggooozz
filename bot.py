#!/usr/bin/env python3
"""
Music Suggest Bot v3 - Full Featured Music Discovery Platform
Uses librosa, MusicBrainz, AcousticBrainz, and Last.fm for intelligent recommendations.
"""

import asyncio
import base64
import html
import logging
import os
import random
import re
import time
import threading
from collections import OrderedDict
from http.server import HTTPServer, BaseHTTPRequestHandler

import aiohttp
from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

if os.path.exists(".env"):
    load_dotenv()

from config import (
    TELEGRAM_BOT_TOKEN, PORT, LASTFM_API_KEY, TELEGRAM_PROXY, AUDD_API_TOKEN,
)
from deezer_helper import DeezerClient, TrackInfo
from audio_analyzer import analyze_audio, AudioFeatures
from musicbrainz_client import MusicBrainzClient, AcousticBrainzFeatures
from lastfm_client import LastfmClient
from similarity_engine import rank_by_similarity, SimilarityResult
from feature_cache import init_cache, get_cached_features, cache_features
from user_prefs import (
    init_db, save_vote, get_user_votes, get_user_rating_stats,
    get_user_top_artists, save_playlist, get_user_playlists, get_playlist,
    update_trivia_score, get_trivia_leaderboard, get_trivia_stats,
    add_to_history, get_user_history, get_top_rated_tracks, get_most_active_users,
    add_to_user_playlist, get_user_playlist, clear_user_playlist,
    get_user_taste_profile, get_user_playlist_artists, get_random_recommendations,
    store_suggestions, get_random_suggestions, count_suggestions,
    set_user_language, get_user_language,
)
from language_detect import detect_language, language_label
from playlist_manager import generate_playlist, format_playlist_text
from taste_profiler import build_taste_profile, format_taste_profile, get_recommendation_weights
from trivia_game import (
    create_trivia_question, start_session, get_session, end_session,
    check_answer, format_question, format_session_stats, TriviaSession,
)
from lyrics_client import LyricsClient, format_lyrics
from card_generator import generate_music_card, generate_comparison_card
from dna_generator import generate_musical_dna
import i18n as i18n_mod
from i18n import label as L, msg as M, supported_langs, set_lang as i18n_set_lang, get_lang

# ═══════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════
from logging_config import setup_logging

# Log to console + bot.log file (DEBUG in file, INFO on console)
setup_logging(level=logging.INFO, log_file="bot.log")
log = logging.getLogger(__name__)

from telegram.request import HTTPXRequest

_http_kwargs = dict(connect_timeout=20.0, read_timeout=15.0, write_timeout=15.0, pool_timeout=5.0)
if TELEGRAM_PROXY:
    _http_kwargs["proxy"] = TELEGRAM_PROXY
_http_request = HTTPXRequest(**_http_kwargs)

# Initialize clients
dz = DeezerClient()
mb = MusicBrainzClient()
lfm = LastfmClient(LASTFM_API_KEY) if LASTFM_API_KEY else None
PM = ParseMode.HTML

# Load Persian genre database
PERSIAN_GENRES = {}
try:
    import json
    with open("persian_genres.json", "r", encoding="utf-8") as f:
        PERSIAN_GENRES = json.load(f)
    log.info("Loaded Persian genre database: %d artists", len(PERSIAN_GENRES))
except Exception as e:
    log.warning("Could not load Persian genre database: %s", e)


def detect_persian_artist(artist_name: str) -> bool:
    """Detect if an artist is likely Persian based on name patterns."""
    # Common Persian name patterns
    persian_patterns = [
        "ghorbani", "shajarian", "nazeri", "aghili", "eftekhari",
        "namjoo", "najafi", "afagh", "yarrahi", "aghili",
        "ebi", "googoosh", "dariush", "forouhar", "ghomayshi",
        "tataloo", "hichkas", "yas", "poupak", "tabori",
        "shahin", "saman", "zedbazi", "saremi", "mankan",
        "virgool", "sadeghi", "chavoshi", "lohrasbi", "khosravi",
        "khorram", "jalili", "ahmadvand", "golab", "esfahani",
        "alizadeh", "kalhor", "motebassem", "derakhshani",
        "lotfi", "babaei", "rajabi", "solati", "hengameh",
        "shahram", "mohsen", "ali", "reza", "amir", "sina",
        "pejman", "mehdi", "homayoun", "siavash", "kaveh",
        "shahin", "yaghmaei", "mehrad", "aslani", "ghanbari",
        "poladi", "shabpareh", "vigen", "delkash", "homeyra",
        "aref", "sattar", "mohebian", "foroughi", "arian",
        "127", "o-hum", "kiosk", "pallett", "hypernova",
        "yellow dogs", "liraz", "samira", "pourya", "nazanin",
        "mahan", "bamdad", "shila", "pegah", "donya", "sara",
        "mina", "neda", "leila", "maryam", "zahra", "somaye",
        "mahsa", "taraneh", "shirin", "golnaz", "parisa",
        "fatemeh", "sedigheh", "arezoo", "nasrin", "vida", "giti"
    ]

    artist_lower = artist_name.lower()
    for pattern in persian_patterns:
        if pattern in artist_lower:
            return True
    return False


def save_new_persian_artist(artist_name: str, song_title: str):
    """Save a newly detected Persian artist to new_persian_artists.json."""
    new_artists_file = "new_persian_artists.json"

    # Load existing data
    new_artists = {}
    try:
        with open(new_artists_file, "r", encoding="utf-8") as f:
            new_artists = json.load(f)
    except FileNotFoundError:
        pass

    # Add if not already in main database or new artists file
    if artist_name not in PERSIAN_GENRES and artist_name not in new_artists:
        new_artists[artist_name] = ["Persian (Auto-detected)"]
        with open(new_artists_file, "w", encoding="utf-8") as f:
            json.dump(new_artists, f, indent=2, ensure_ascii=False)
        log.info("Added new Persian artist: %s (from song: %s)", artist_name, song_title)


class TTLCache:
    """Simple TTL-based cache with max size."""

    def __init__(self, maxsize: int = 1000, ttl: int = 300):
        self._cache: OrderedDict[int, dict] = OrderedDict()
        self._timestamps: dict[int, float] = {}
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key: int) -> dict:
        if key in self._cache:
            if time.time() - self._timestamps[key] < self._ttl:
                self._cache.move_to_end(key)
                return self._cache[key]
            else:
                del self._cache[key]
                del self._timestamps[key]
        return {}

    def set(self, key: int, value: dict):
        if key in self._cache:
            del self._cache[key]
        elif len(self._cache) >= self._maxsize:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            del self._timestamps[oldest]
        self._cache[key] = value
        self._timestamps[key] = time.time()

    def pop(self, key: int, default=None):
        self._timestamps.pop(key, None)
        return self._cache.pop(key, default)


_user_state = TTLCache(maxsize=1000, ttl=600)

# Playlist mode tracking
_playlist_mode = {}  # user_id: True/False
_pending_songs = {}  # user_id: list of songs waiting to be processed
_failed_songs = {}  # user_id: list of songs that failed

def log_step(step_num, user_id, message):
    """Log a step in the playlist process."""
    log.info(f"[STEP {step_num}] User {user_id}: {message}")


def h(text) -> str:
    return html.escape(str(text))


# ═══════════════════════════════════════════════════
# Persian Detection & Translation
# ═══════════════════════════════════════════════════

def has_persian(text: str) -> bool:
    for char in text:
        code = ord(char)
        if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F or 0xFB50 <= code <= 0xFDFF:
            return True
    return False


PERSIAN_ARTISTS = {
    "محسن نامجو": "Mohsen Namjoo",
    "کاوه آفاق": "Kaveh Afagh",
    "داریوش": "Dariush",
    "گوگوش": "Googoosh",
    "ابی": "Ebi",
    "شجریان": "Shajarian",
    "محسن چاوشی": "Mohsen Chavoshi",
    "رضا بهرام": "Reza Bahram",
    "امیر تتلو": "Amir Tataloo",
    "تتلو": "Tataloo",
}


def find_persian_english(text: str) -> str:
    for persian, english in PERSIAN_ARTISTS.items():
        if persian in text:
            return english
    return ""


def clean_song_name(name: str) -> str:
    """Clean a song name for better search results."""
    # Remove file extensions
    name = re.sub(r'\.(mp3|wav|flac|m4a|ogg|wma|webm)$', '', name, flags=re.IGNORECASE)
    # Remove trailing numbers and dots (like -320, -256, (320))
    name = re.sub(r'[\s]*[-_]?\s*\d+\s*$', '', name)
    name = re.sub(r'\(\d+\)$', '', name)
    # Replace dashes and underscores with spaces
    name = name.replace("-", " ").replace("_", " ")
    # Remove extra spaces
    name = ' '.join(name.split())
    # Remove leading numbers
    name = re.sub(r'^\d+[\s.]', '', name)
    return name.strip()


# ═══════════════════════════════════════════════════
# Download link helper
# ═══════════════════════════════════════════════════

def make_download_link(bot_username: str) -> str:
    """Create a link to open @DeezerMusicBot."""
    return f"https://t.me/{bot_username}"


# ═══════════════════════════════════════════════════
# Health server
# ═══════════════════════════════════════════════════

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_http_server():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()


# ═══════════════════════════════════════════════════
# Keyboards
# ═══════════════════════════════════════════════════

def _search_keyboard(results: list[TrackInfo], query: str = "") -> InlineKeyboardMarkup:
    buttons = []

    # First button: "Original version" - tries to find the exact song
    buttons.append([InlineKeyboardButton(f"🎵 Original: {query[:35]}", callback_data="pick_original")])

    # Other results - 1 per line
    for i, t in enumerate(results):
        label = f"🎵 {t.title} - {t.artist}"
        if len(label) > 40:
            label = label[:37] + "..."
        buttons.append([InlineKeyboardButton(label, callback_data=f"pick_{i}")])

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


def _main_menu_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    """Main menu keyboard under chat box."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(label("search", lang)), KeyboardButton(label("add_playlist", lang))],
            [KeyboardButton(label("my_playlist", lang)), KeyboardButton(label("for_me", lang))],
            [KeyboardButton(label("trivia", lang)), KeyboardButton(label("language", lang))],
        ],
        resize_keyboard=True
    )


def _playlist_mode_keyboard(count: int, lang: str = "en") -> ReplyKeyboardMarkup:
    """Keyboard shown when in playlist mode."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(f"{label('done', lang)} ({count} songs)")],
            [KeyboardButton(label("cancel", lang)), KeyboardButton(label("main_menu", lang))],
        ],
        resize_keyboard=True
    )


def _similarity_keyboard(result: SimilarityResult) -> InlineKeyboardMarkup:
    buttons = []
    buttons.append([InlineKeyboardButton("⬇️ Open DeezerMusicBot", url=make_download_link("DeezerMusicBot"))])
    buttons.append([InlineKeyboardButton("🔄 Search Again", callback_data="search_again")])
    return InlineKeyboardMarkup(buttons)


def _vote_keyboard(track_id: int, title: str = "", artist: str = "") -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("⭐1", callback_data=f"vote_{track_id}_1"),
            InlineKeyboardButton("⭐2", callback_data=f"vote_{track_id}_2"),
            InlineKeyboardButton("⭐3", callback_data=f"vote_{track_id}_3"),
            InlineKeyboardButton("⭐4", callback_data=f"vote_{track_id}_4"),
            InlineKeyboardButton("⭐5", callback_data=f"vote_{track_id}_5"),
        ]
    ]
    buttons.append([InlineKeyboardButton("⬇️ Open DeezerMusicBot", url=make_download_link("DeezerMusicBot"))])
    return InlineKeyboardMarkup(buttons)


def _meforyou_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Keyboard under the For Me results: open DeezerMusicBot + fresh batch."""
    buttons = [
        [InlineKeyboardButton("⬇️ Open DeezerMusicBot", url=make_download_link("DeezerMusicBot"))],
        [InlineKeyboardButton(label("refresh", lang), callback_data="meforyou_refresh")],
    ]
    return InlineKeyboardMarkup(buttons)


def format_similarity_score(score: float) -> str:
    """Format similarity score as percentage."""
    percentage = int(score * 100)
    if percentage >= 90:
        return f"🔥 {percentage}%"
    elif percentage >= 75:
        return f"🎵 {percentage}%"
    elif percentage >= 50:
        return f"🎶 {percentage}%"
    else:
        return f"📻 {percentage}%"


# ═══════════════════════════════════════════════════
# Analysis Pipeline
# ═══════════════════════════════════════════════════

async def analyze_track(track: TrackInfo, fast_mode: bool = False) -> dict:
    """
    Analyze a track using all available sources.
    Returns dict with audio_features, acoustic_features, lastfm_data.
    Caches results so next time is instant.

    fast_mode: If True, skips librosa (slower) and only uses MusicBrainz/AcousticBrainz
    """
    # Check cache first. A hit is only usable for similarity scoring if it
    # carries audio or acoustic features; tags alone aren't enough (comparing
    # against None features yields 0.00 scores).
    cached = await get_cached_features(track.id)
    if cached and (cached.get("audio_features") or cached.get("acoustic_features")):
        log.info("Cache hit for: %s - %s", track.artist, track.title)
        return cached
    if cached:
        # Cache entry exists but holds no usable features (e.g. old poisoned
        # entry, or analysis failed before) -> re-analyze to fill it in.
        log.info("Cache entry without features for %s - %s, re-analyzing (track %s)",
                 track.artist, track.title, track.id)

    log.info("Analyzing track: %s - %s (fast=%s)", track.artist, track.title, fast_mode)

    # Parallel analysis
    tasks = []

    # Audio analysis (librosa) - skip in fast mode
    if not fast_mode and track.preview_url:
        tasks.append(analyze_audio(track.preview_url))
    else:
        tasks.append(_null_coro())

    # MusicBrainz + AcousticBrainz
    async def get_mb_features():
        try:
            mbid = await mb.search_recording(track.artist, track.title)
            if mbid:
                acoustic = await mb.get_acoustic_features(mbid)
                return {"musicbrainz_id": mbid, "acoustic_features": acoustic}
        except Exception as e:
            log.warning("MusicBrainz error: %s", e)
        return {"musicbrainz_id": None, "acoustic_features": None}

    tasks.append(get_mb_features())

    # Last.fm
    if not fast_mode and lfm:
        async def get_lastfm_data():
            try:
                info = await lfm.get_track_info(track.artist, track.title)
                tags = info.tags if info else []
                return {"tags": tags}
            except Exception:
                return {"tags": []}
        tasks.append(get_lastfm_data())
    else:
        tasks.append(_null_coro())

    # Run all analyses concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    audio_features = results[0] if not isinstance(results[0], Exception) else None
    mb_data = results[1] if not isinstance(results[1], Exception) else {}
    lastfm_data = results[2] if not isinstance(results[2], Exception) else {}

    log.info("Analysis results for %s - %s:", track.artist, track.title)
    log.info("  Audio features: %s", "OK" if audio_features else "SKIPPED" if fast_mode else "FAILED")
    log.info("  MusicBrainz: %s", "OK" if mb_data.get("musicbrainz_id") else "NOT FOUND")
    log.info("  AcousticBrainz: %s", "OK" if mb_data.get("acoustic_features") else "NOT FOUND")
    log.info("  Last.fm tags: %d", len(lastfm_data.get("tags", [])))

    # Ensure mb_data is a dict
    if not isinstance(mb_data, dict):
        mb_data = {}
    if not isinstance(lastfm_data, dict):
        lastfm_data = {}

    # If librosa was skipped (fast_mode) but Deezer provides a BPM, synthesize a
    # minimal AudioFeatures so similarity still has tempo+energy signal.
    if audio_features is None and track.bpm:
        af = AudioFeatures()
        af.bpm = float(track.bpm)
        audio_features = af
        log.info("[FLOW] fast_mode: using Deezer BPM %.1f for %s - %s", af.bpm, track.artist, track.title)

    # Cache the results
    await cache_features(
        track.id, track.title, track.artist,
        audio_features,
        mb_data.get("acoustic_features"),
        mb_data.get("musicbrainz_id"),
        lastfm_data.get("tags", []),
    )

    return {
        "audio_features": audio_features,
        "acoustic_features": mb_data.get("acoustic_features"),
        "musicbrainz_id": mb_data.get("musicbrainz_id"),
        "lastfm_tags": lastfm_data.get("tags", []),
    }


async def _null_coro():
    return None


async def find_similar_tracks(
    target_track: TrackInfo,
    target_features: dict,
    candidate_tracks: list[TrackInfo],
) -> list[SimilarityResult]:
    """
    Find similar tracks by analyzing all candidates and comparing features.
    Uses caching - tracks analyzed before are instant.
    """
    # Analyze all candidates (cache will speed up repeated searches)
    semaphore = asyncio.Semaphore(3)

    async def analyze_with_limit(track):
        async with semaphore:
            return await analyze_track(track)

    # Analyze candidates
    candidate_features = await asyncio.gather(
        *[analyze_with_limit(t) for t in candidate_tracks],
        return_exceptions=True
    )

    # Build candidate list for ranking
    candidates = []
    for i, (track, features) in enumerate(zip(candidate_tracks, candidate_features)):
        if isinstance(features, Exception):
            continue
        candidates.append({
            "track_id": track.id,
            "title": track.title,
            "artist": track.artist,
            "preview_url": track.preview_url or "",
            "album_art": track.album_art or "",
            "deezer_url": track.deezer_url or "",
            "audio_features": features.get("audio_features"),
            "acoustic_features": features.get("acoustic_features"),
            "lastfm_match": 0.0,
        })

    # Rank by similarity
    results = rank_by_similarity(
        target_features.get("audio_features"),
        target_features.get("acoustic_features"),
        candidates,
    )

    return results


# ═══════════════════════════════════════════════════
# Handlers
# ═══════════════════════════════════════════════════

async def _ensure_lang(user_id: int):
    """Load a user's persisted language into the i18n cache."""
    if user_id not in i18n_mod._user_lang:
        try:
            i18n_set_lang(user_id, await get_user_language(user_id))
        except Exception:
            i18n_set_lang(user_id, "en")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    _playlist_mode[user_id] = False
    await _ensure_lang(user_id)
    lang = get_lang(user_id)
    await update.message.reply_text(
        M("start_hero", lang),
        parse_mode=PM,
        reply_markup=_main_menu_keyboard(lang),
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if not query:
        return

    user_id = update.effective_user.id
    log_step(1, user_id, f"Received text: {query[:50]}...")
    await _ensure_lang(user_id)

    # Handle keyboard buttons (match any of the bot's languages)
    lang = get_lang(user_id)
    if query in (label("search", "en"), label("search", "fa"), "🔍 Search"):
        _playlist_mode[user_id] = False
        await update.message.reply_text("🔍 Type a song name to search:")
        return

    if query == label("add_playlist", lang):
        log_step(2, user_id, "Entering playlist mode")
        _playlist_mode[user_id] = True
        _pending_songs[user_id] = []
        _failed_songs[user_id] = []
        await update.message.reply_text(
            "📋 <b>Playlist Mode ON</b>\n\n"
            "Send song names one by one:\n"
            "  • <code>Bohemian Rhapsody Queen</code>\n"
            "  • <code>Hotel California Eagles</code>\n\n"
            "I'll automatically add each song.\n"
            "When done, tap <b>Done</b> below!",
            parse_mode=PM,
            reply_markup=_playlist_mode_keyboard(0, lang),
        )
        return

    if query == label("my_playlist", lang):
        _playlist_mode[user_id] = False
        await cmd_myplaylist(update, context)
        return

    if query == label("for_me", lang):
        _playlist_mode[user_id] = False
        await cmd_meforyou(update, context)
        return

    if query == label("trivia", lang):
        _playlist_mode[user_id] = False
        await cmd_trivia(update, context)
        return

    if query == label("language", lang):
        _playlist_mode[user_id] = False
        await _show_language_picker(update, context)
        return

    # Handle playlist mode
    if _playlist_mode.get(user_id, False):
        if query.startswith(label("done", lang)) or query.startswith("✅ Done"):
            log_step(3, user_id, "Done button pressed, starting processing")
            await cmd_done(update, context)
            return
        if query in (label("cancel", lang), label("main_menu", lang), "❌ Cancel", "🔙 Main Menu"):
            log_step(3, user_id, "Exiting playlist mode")
            _playlist_mode[user_id] = False
            _failed_songs.pop(user_id, None)
            _pending_songs.pop(user_id, None)
            await update.message.reply_text(
                "❌ Playlist mode exited.",
                reply_markup=_main_menu_keyboard(),
            )
            return

        # Just store the song, don't process yet
        log_step(3, user_id, f"Storing song: {query[:50]}")
        _pending_songs.setdefault(user_id, []).append(query)
        count = len(_pending_songs[user_id])
        await update.message.reply_text(
            f"📝 <b>{count}.</b> {h(query)}",
            parse_mode=PM,
            reply_markup=_playlist_mode_keyboard(count),
        )
        return

    # Handle "Search Again" response
    if query.lower() in ["search again", "search", "again"]:
        await update.message.reply_text("🔍 Type a song name to search:")
        return

    await update.message.chat.send_action("typing")

    # Clean up search query - replace dashes, underscores, remove file extensions
    search_query = query.replace("-", " ").replace("_", " ")
    # Remove file extensions like .mp3, .wav, etc.
    search_query = re.sub(r'\.(mp3|wav|flac|m4a|ogg|wma)$', '', search_query, flags=re.IGNORECASE)
    # Remove trailing numbers and dots (like -320, -256, etc.)
    search_query = re.sub(r'[\s]*[-_]?\s*\d+\s*$', '', search_query)
    # Remove extra spaces
    search_query = ' '.join(search_query.split())

    # Check for Persian
    if has_persian(query):
        english = find_persian_english(query)
        if english:
            search_query = english
            log.info("Persian '%s' -> English '%s'", query, english)
            await update.message.reply_text(f"🔍 Found English name: <b>{h(english)}</b>", parse_mode=PM)

    # Search Deezer - try to find correct artist
    try:
        raw_results = await dz.search(search_query, limit=5)

        # Prioritize clean (non-live / non-remix) versions first so users don't
        # land on live tracks (which break similarity: no radio, no features).
        live_markers = ("live", "remaster", "remix", "edit", "version", "deluxe", "reissue", "anniversary")
        clean = [t for t in raw_results if not any(m in t.title.lower() for m in live_markers)]
        results = clean + [t for t in raw_results if any(m in t.title.lower() for m in live_markers)]
        # Deduplicate by (title, artist_id)
        seen_sr = set()
        deduped = []
        for t in results:
            key = (t.title.lower(), t.artist_id)
            if key not in seen_sr:
                seen_sr.add(key)
                deduped.append(t)
        results = deduped[:5]
        log.info("[SEARCH] raw=%d, clean-first reorder done -> %d shown", len(raw_results), len(results))
        
        # If we found results, try to verify the artist ID
        if results:
            # Check if there are other tracks by a similar artist name
            first_artist = results[0].artist
            first_artist_id = results[0].artist_id
            
            # Search for artist specifically to get correct ID
            try:
                artist_search = await dz.search(f"artist:{first_artist}", limit=3)
                if artist_search:
                    # Find the most popular track by this artist
                    for track in artist_search:
                        if track.artist.lower() == first_artist.lower():
                            if track.artist_id != first_artist_id:
                                log.info("Found correct artist ID: %d for %s (was %d)", 
                                        track.artist_id, first_artist, first_artist_id)
                                # Update the artist_id in all results
                                for r in results:
                                    if r.artist.lower() == first_artist.lower():
                                        r.artist_id = track.artist_id
                            break
            except Exception:
                pass
    except Exception as e:
        log.warning("Search failed: %s", e)
        await update.message.reply_text("Search failed. Try again.")
        return

    if not results:
        if has_persian(query) and search_query == query:
            await update.message.reply_text("No results found for this Persian name. Try the English name.")
        else:
            await update.message.reply_text("No results found. Try another search.")
        return

    _user_state.set(update.effective_chat.id, {"results": results, "query": query, "step": "select"})
    caption = f"🔍 <b>Results for:</b> <i>{h(query)}</i>\n\nWhich one did you mean?"
    await update.message.reply_text(caption, reply_markup=_search_keyboard(results, query), parse_mode=PM)


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle audio/voice messages - recognize the song."""
    user_id = update.effective_user.id

    # In playlist mode, just store the filename
    if _playlist_mode.get(user_id, False):
        audio = update.message.effective_attachment
        if hasattr(audio, "file_name") and audio.file_name:
            raw = audio.file_name.rsplit(".", 1)[0]
            query = raw.replace("-", " ").replace("_", " ")
            _pending_songs.setdefault(user_id, []).append(query)
            count = len(_pending_songs[user_id])
            await update.message.reply_text(
                f"📝 <b>{count}.</b> {h(query)}",
                parse_mode=PM,
                reply_markup=_playlist_mode_keyboard(count),
            )
        else:
            await update.message.reply_text(
                "❌ Can't read filename. Send the song name as text instead.",
                reply_markup=_playlist_mode_keyboard(len(_pending_songs.get(user_id, []))),
            )
        return

    await update.message.chat.send_action("typing")
    audio = update.message.effective_attachment
    query, source = "", ""

    # Try to get info from filename
    if hasattr(audio, "file_name") and audio.file_name:
        raw = audio.file_name.rsplit(".", 1)[0]
        if " - " in raw:
            parts = raw.split(" - ", 1)
            query, source = f"{parts[0]} {parts[1]}", "filename"
        elif "_" in raw:
            query, source = raw.replace("_", " "), "filename"
        else:
            query, source = raw, "filename"

    # Try to get info from metadata
    if hasattr(audio, "performer") and audio.performer:
        title_part = getattr(audio, "title", "") or ""
        if title_part:
            query, source = f"{title_part} {audio.performer}", "metadata"
        elif not query:
            query, source = audio.performer, "metadata"

    if query and len(query) >= 3:
        await update.message.reply_text(f"🔍 <b>Searching:</b> <i>{h(query)}</i>...", parse_mode=PM)

        # Try Persian translation if needed
        search_query = query
        if has_persian(query):
            english = find_persian_english(query)
            if english:
                search_query = english

        try:
            results = await dz.search(search_query, limit=5)
        except Exception:
            results = []
        if results:
            _user_state.set(update.effective_chat.id, {"results": results, "query": query})
            await update.message.reply_text(
                f"🔍 <b>Results from {h(source)}:</b>",
                reply_markup=_search_keyboard(results, query),
                parse_mode=PM
            )
            return

    # If no info from metadata, try AudD recognition
    if AUDD_API_TOKEN:
        await update.message.reply_text("🎤 Recognising audio...")
        import io
        try:
            file = await audio.get_file()
            file_bytes = await file.download_as_bytearray()
        except Exception:
            await update.message.reply_text("Couldn't download audio. Type the song name instead.")
            return
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field("api_token", AUDD_API_TOKEN)
                data.add_field("return", "deezer")
                data.add_field("file", io.BytesIO(file_bytes), filename="audio.mp3", content_type="audio/mpeg")
                async with session.post("https://api.audd.io/", data=data, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    result = await resp.json()
        except Exception:
            await update.message.reply_text("Type the song name instead.")
            return
        if result.get("error", {}).get("error_code") == 900:
            await update.message.reply_text("AudD token invalid. Type the song name instead.")
            return
        if result.get("status") == "success" and result.get("result"):
            td = result["result"]
            recognized_name = f"{td.get('title', '')} {td.get('artist', '')}"
            await update.message.reply_text(
                f"🎤 I heard: <b>{h(td.get('title', ''))}</b> - <b>{h(td.get('artist', ''))}</b>",
                parse_mode=PM,
            )
            # Search for the recognized track
            try:
                results = await dz.search(recognized_name, limit=5)
                if results:
                    _user_state.set(update.effective_chat.id, {"results": results, "query": recognized_name})
                    await update.message.reply_text(
                        "Which one did you mean?",
                        reply_markup=_search_keyboard(results, recognized_name),
                        parse_mode=PM
                    )
                    return
            except Exception:
                pass

    await update.message.reply_text("Couldn't identify the song. Type the song name instead.")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    data = query.data
    log.info("Callback received: chat_id=%s, data=%s", chat_id, data)

    # Answer immediately to prevent timeout
    await query.answer()

    state = _user_state.get(chat_id)

    if data == "cancel":
        await query.edit_message_text("❌ Cancelled.")
        _user_state.pop(chat_id, None)
        return

    # Confirm clearing the playlist (destructive)
    if data == "confirm_clear":
        uid = update.effective_user.id
        lang = get_lang(uid)
        try:
            await clear_user_playlist(uid)
            await query.edit_message_text(
                "🗑️ Playlist cleared! Add songs again with ➕ Add to Playlist.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton(label("main_menu", lang), callback_data="back_main")]]
                ),
            )
        except Exception as e:
            log.error("confirm_clear failed: %s", e)
            await query.edit_message_text("❌ Couldn't clear playlist. Try again.")
        return

    if data == "back_main":
        uid = update.effective_user.id
        lang = get_lang(uid)
        await query.edit_message_text(
            M("start_hero", lang), parse_mode=PM,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠", callback_data="noop")]])
        )
        return

    if data == "noop":
        return

    if data == "search_again":
        await query.edit_message_text("🔍 Type a song name to search:")
        _user_state.pop(chat_id, None)
        return

    # Language selection
    if data.startswith("lang_"):
        code = data.split("_", 1)[1]
        uid = update.effective_user.id
        i18n_set_lang(uid, code)
        try:
            await set_user_language(uid, code)
        except Exception as e:
            log.warning("set_user_language failed: %s", e)
        name = supported_langs().get(code, code)
        await query.edit_message_text(f"✅ Language set: {name}\nزبان تنظیم شد: {name}")
        # Refresh the main keyboard in the new language
        await update.effective_chat.send_message(
            M("start_hero", code),
            parse_mode=PM,
            reply_markup=_main_menu_keyboard(code),
        )
        return

    # Fresh batch for For Me
    if data == "meforyou_refresh":
        await query.edit_message_text("🎯 Refreshing your batch...")
        # Re-run the full For Me flow on the same chat/message
        try:
            await cmd_meforyou(update, context)
        except Exception as e:
            log.error("meforyou_refresh failed: %s", e, exc_info=True)
            await query.edit_message_text("❌ Couldn't refresh. Tap 🎯 For Me again.")
        return

    # Handle votes
    if data.startswith("vote_"):
        try:
            parts = data.split("_")
            track_id = int(parts[1])
            rating = int(parts[2])
            user_id = update.effective_user.id

            track_title = state.get("last_track_title", "Unknown") if state else "Unknown"
            track_artist = state.get("last_track_artist", "Unknown") if state else "Unknown"
            log.info("Saving vote: user=%s, track=%s, rating=%s", user_id, track_id, rating)
            await save_vote(user_id, track_id, track_title, track_artist, rating)

            stars = "⭐" * rating
            await query.edit_message_text(f"✅ <b>Rated:</b> {stars} ({rating}/5)", parse_mode=PM)
            
            # Delete vote message after 3 seconds to reduce clutter
            async def delete_vote_message():
                await asyncio.sleep(3)
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
                except Exception:
                    pass
            asyncio.create_task(delete_vote_message())
            
            log.info("Vote saved successfully")
        except Exception as e:
            log.error("Error saving vote: %s", e)
            await query.answer("Error saving vote. Try again.")
        return

    # Handle "Original version" selection
    if data == "pick_original":
        query_text = state.get("query", "") if state else ""
        if not query_text:
            await query.edit_message_text("No search query found. Try again.")
            _user_state.pop(chat_id, None)
            return

        # Try to find the original version (not live, not remastered)
        await query.edit_message_text(f"🔍 Searching for original version of: {h(query_text)}...")

        try:
            # Search with "original" keyword
            results = await dz.search(f"{query_text}", limit=10)

            # Filter for original versions (not live, not remastered)
            original = None
            for track in results:
                title_lower = track.title.lower()
                # Skip live, remastered, deluxe, etc.
                if any(x in title_lower for x in ["live", "remaster", "deluxe", "version", "edit", "remix"]):
                    continue
                original = track
                break

            # If no clean original found, use first result as reference
            if not original and results:
                original = results[0]

            if original:
                selected_track = original
            else:
                await query.edit_message_text("Couldn't find the original version. Try searching again.")
                _user_state.pop(chat_id, None)
                return

        except Exception as e:
            log.error("Original search failed: %s", e)
            await query.edit_message_text("Search failed. Try again.")
            _user_state.pop(chat_id, None)
            return

    # Handle track selection by index
    elif data.startswith("pick_"):
        idx = int(data.split("_")[1])
        results: list[TrackInfo] = state.get("results", []) if state else []
        log.info("Pick handler: idx=%s, results_count=%s", idx, len(results))

        if idx < 0 or idx >= len(results):
            await query.edit_message_text("⏰ Expired. Try searching again.")
            _user_state.pop(chat_id, None)
            return

        selected_track = results[idx]

    else:
        return

    # ═══════════════════════════════════════════════════
    # ONE-SHOT: Analyze + Build + Send Complete Message
    # ═══════════════════════════════════════════════════

    # Fetch full track details with genres
    try:
        full_track = await dz.get_track(selected_track.id)
        if full_track:
            selected_track = full_track
            log.info("Fetched full track: %s - %s (genres: %s, artist_id: %d)", 
                    selected_track.artist, selected_track.title, selected_track.genres, selected_track.artist_id)

            # Try to find correct artist ID if we have few same-artist tracks
            # Search for artist by name to get correct ID
            try:
                # Try to find correct artist ID by searching both spellings
                artist_name = selected_track.artist
                
                # Common spelling corrections for Persian names
                spelling_corrections = {
                    "Iranj Bastami": "Iraj Bastami",
                    "Iraj Bastami": "Iranj Bastami",
                }
                
                best_artist_id = selected_track.artist_id
                best_track_count = 0
                
                # Search current spelling
                search_results = await dz.search(artist_name, limit=10)
                if search_results:
                    from collections import Counter
                    artist_ids = [t.artist_id for t in search_results]
                    artist_id_counts = Counter(artist_ids)
                    most_common_id, count = artist_id_counts.most_common(1)[0]
                    if count > best_track_count:
                        best_artist_id = most_common_id
                        best_track_count = count
                        log.info("Search '%s': found %d tracks, best ID=%d (count=%d)", 
                                artist_name, len(search_results), most_common_id, count)
                
                # Try corrected spelling
                if artist_name in spelling_corrections:
                    corrected_name = spelling_corrections[artist_name]
                    corrected_results = await dz.search(corrected_name, limit=10)
                    if corrected_results:
                        artist_ids = [t.artist_id for t in corrected_results]
                        artist_id_counts = Counter(artist_ids)
                        most_common_id, count = artist_id_counts.most_common(1)[0]
                        if count > best_track_count:
                            best_artist_id = most_common_id
                            best_track_count = count
                            log.info("Search '%s' (corrected): found %d tracks, best ID=%d (count=%d)", 
                                    corrected_name, len(corrected_results), most_common_id, count)
                
                if best_artist_id != selected_track.artist_id:
                    log.info("Corrected artist_id from %d to %d for %s", 
                            selected_track.artist_id, best_artist_id, artist_name)
                    selected_track.artist_id = best_artist_id
                    
            except Exception as e:
                log.warning("Artist ID correction failed: %s", e)

            # Auto-detect Persian artists
            if not selected_track.genres and detect_persian_artist(selected_track.artist):
                save_new_persian_artist(selected_track.artist, selected_track.title)
    except Exception as e:
        log.error("Failed to fetch full track: %s", e)

    await query.edit_message_text(
        f"🎵 <b>{h(selected_track.title)}</b> - {h(selected_track.artist)}\n\n"
        f"🔍 Analyzing audio features...",
        parse_mode=PM
    )

    # Analyze main track (for features)
    target_features = {}
    try:
        target_features = await analyze_track(selected_track) or {}
        log.info("[FLOW] main track analyzed: audio=%s acoustic=%s",
                 bool(target_features.get("audio_features")), bool(target_features.get("acoustic_features")))
    except Exception as e:
        log.error("Main track analysis failed: %s", e, exc_info=True)

    # Get similar tracks
    same_artist_tracks = []
    diff_artist_tracks = []
    seen_titles = {selected_track.title.lower()}

    def is_duplicate(track):
        title_lower = track.title.lower()
        if title_lower in seen_titles:
            return True
        base_title = title_lower.split("(")[0].split("-")[0].strip()
        for seen in seen_titles:
            seen_base = seen.split("(")[0].split("-")[0].strip()
            if base_title == seen_base and base_title:
                return True
        return False

    # 1. Last.fm similar tracks (PRIMARY source - Deezer radio is dead, see /track/{id}/radio)
    if lfm:
        try:
            lastfm_similar = await lfm.get_similar_tracks(selected_track.artist, selected_track.title, limit=10)
            log.info("[FLOW] Last.fm similar for %s: %d found", selected_track.title, len(lastfm_similar))
            for ls in lastfm_similar[:8]:
                try:
                    ls_results = await dz.search(f"{ls.name} {ls.artist}", limit=1)
                    if ls_results and not is_duplicate(ls_results[0]):
                        track = ls_results[0]
                        if track.artist_id != selected_track.artist_id:
                            track.lastfm_match = ls.match
                            diff_artist_tracks.append((track, ls.match))
                            seen_titles.add(track.title.lower())
                except Exception as e:
                    log.warning("[FLOW] Last.fm->Deezer lookup failed for %s - %s: %s", ls.name, ls.artist, e)
        except Exception as e:
            log.error("[FLOW] Last.fm similar error: %s", e, exc_info=True)

    # 2. Deezer radio (try to get more tracks; often returns 0 now)
    try:
        similar_radio = await dz.get_similar(selected_track.id, limit=20)
        log.info("[FLOW] Deezer radio for %s: found %d tracks", selected_track.title, len(similar_radio))
        for t in similar_radio:
            if t.artist_id != selected_track.artist_id and not is_duplicate(t):
                diff_artist_tracks.append((t, 0.0))
                seen_titles.add(t.title.lower())
    except Exception as e:
        log.error("Error getting Deezer radio: %s", e)

    # 3. Same artist tracks (try to get more)
    try:
        artist_tracks = await dz.get_artist_top(selected_track.artist_id, limit=10)
        log.info("Same artist tracks for %s (ID: %d): %d found", selected_track.artist, selected_track.artist_id, len(artist_tracks))
        for t in artist_tracks:
            if t.id != selected_track.id and not is_duplicate(t):
                same_artist_tracks.append(t)
                seen_titles.add(t.title.lower())
                log.info("  Added same artist: %s - %s", t.artist, t.title)
    except Exception as e:
        log.error("Error getting same artist tracks: %s", e)

    # If no tracks found, try searching by artist name
    if not same_artist_tracks and not diff_artist_tracks:
        log.info("No tracks found from API, trying search by artist name...")
        try:
            artist_search = await dz.search(selected_track.artist, limit=10)
            log.info("Artist search found %d tracks", len(artist_search))
            for t in artist_search:
                if t.id != selected_track.id and not is_duplicate(t):
                    if t.artist_id == selected_track.artist_id:
                        same_artist_tracks.append(t)
                    else:
                        diff_artist_tracks.append((t, 0.0))
                    seen_titles.add(t.title.lower())
        except Exception as e:
            log.error("Error searching by artist: %s", e, exc_info=True)

    # Combine - try to get 6 total, mixing same artist and different artists.
    # Different-artist tracks carry a Last.fm match score; best matches first.
    log.info("Same artist tracks found: %d", len(same_artist_tracks))
    log.info("Different artist tracks found: %d", len(diff_artist_tracks))
    diff_artist_tracks.sort(key=lambda x: x[1], reverse=True)
    diff_artist_tracks = [t for t, _ in diff_artist_tracks]

    similar_tracks = []
    # Add up to 3 same artist tracks
    for t in same_artist_tracks[:3]:
        similar_tracks.append(t)
    # Add up to 3 different artist tracks
    for t in diff_artist_tracks[:3]:
        similar_tracks.append(t)
    # If still less than 6, add more from either list
    for t in same_artist_tracks[3:]:
        if len(similar_tracks) >= 6:
            break
        similar_tracks.append(t)
    for t in diff_artist_tracks[3:]:
        if len(similar_tracks) >= 6:
            break
        similar_tracks.append(t)

    log.info("Total similar tracks: %d", len(similar_tracks))

    if not similar_tracks:
        await query.edit_message_text("❌ No similar tracks found.\n\nTry searching for a different song.")
        _user_state.pop(chat_id, None)
        return

    top_tracks = similar_tracks[:6]

    # Analyze similar tracks (fast mode: use cached features; only analyze from
    # scratch if not cached. Full librosa on every candidate is what made this
    # flow take 1-2 minutes.)
    candidate_features = {}
    sem = asyncio.Semaphore(3)

    async def _analyze_candidate(track):
        async with sem:
            try:
                return track.id, await analyze_track(track, fast_mode=True)
            except Exception as e:
                log.warning("[FLOW] candidate analysis failed for %s - %s: %s", track.artist, track.title, e)
                return track.id, None

    for tid, feats in await asyncio.gather(*[_analyze_candidate(t) for t in top_tracks]):
        if feats:
            candidate_features[tid] = feats
    log.info("[FLOW] candidate features ready: %d/%d", len(candidate_features), len(top_tracks))

    # Build candidates for scoring
    candidates = []
    for track in top_tracks:
        features = candidate_features.get(track.id) or {}
        audio_feat = features.get("audio_features") if isinstance(features, dict) else None
        acoustic_feat = features.get("acoustic_features") if isinstance(features, dict) else None
        lastfm_match = getattr(track, "lastfm_match", 0.0) or 0.0
        candidates.append({
            "track_id": track.id,
            "title": track.title,
            "artist": track.artist,
            "preview_url": track.preview_url or "",
            "album_art": track.album_art or "",
            "deezer_url": track.deezer_url or "",
            "audio_features": audio_feat,
            "acoustic_features": acoustic_feat,
            "lastfm_match": lastfm_match,
        })

    # Calculate similarity scores
    target_audio = target_features.get("audio_features") if isinstance(target_features, dict) else None
    target_acoustic = target_features.get("acoustic_features") if isinstance(target_features, dict) else None
    log.info("Similarity calc: target_audio=%s, target_acoustic=%s, candidates=%d",
             "YES" if target_audio else "NO", "YES" if target_acoustic else "NO", len(candidates))
    results = rank_by_similarity(target_audio, target_acoustic, candidates)
    log.info("Similarity scores: %s", [(r.title, r.similarity_score) for r in results[:3]])

    # ═══════════════════════════════════════════════════
    # BUILD COMPLETE MESSAGE WITH FEATURES
    # ═══════════════════════════════════════════════════

    lines = [
        "━━━ <b>Selected Track</b> ━━━",
        "",
        f"🎵 <b>{h(selected_track.title)}</b>",
        f"👤 {h(selected_track.artist)}",
        f"💿 {h(selected_track.album)}",
    ]

    # Add features
    features_text = []
    log.info("Building features - target_audio: %s, genres: %s", "YES" if target_audio else "NO", selected_track.genres)

    # From librosa
    if target_audio:
        if target_audio.bpm > 0:
            features_text.append(f"🥁 {target_audio.bpm:.0f} BPM")
        if target_audio.key:
            features_text.append(f"🎵 Key: {target_audio.key} {target_audio.scale}")
        if target_audio.rms_energy > 0:
            features_text.append(f"⚡ Energy: {target_audio.rms_energy:.2f}")

    # Get genre from multiple sources
    genre_found = False

    # 1. Try Persian genre database FIRST (most accurate for Persian artists)
    artist_name = selected_track.artist
    if artist_name in PERSIAN_GENRES:
        features_text.append(f"🎸 {PERSIAN_GENRES[artist_name][0]}")
        genre_found = True

    # 2. Try Deezer genres (artist endpoint no longer returns genres; use track genre_id if present)
    if not genre_found:
        if selected_track.genres:
            features_text.append(f"🎸 {', '.join(selected_track.genres[:2])}")
            genre_found = True
        else:
            # Track-level genre fallback: use the track's explicit_lyrics/genre via the raw API is
            # unreliable; Last.fm tags below are the reliable source.
            log.info("[GENRE] Deezer genres empty for %s - %s", selected_track.artist, selected_track.title)

    # 3. Try Last.fm artist tags (reliable even when Deezer genres are empty)
    if not genre_found and lfm:
        try:
            artist_tags = await lfm.get_artist_top_tags(selected_track.artist)
            if artist_tags:
                # Filter for genre-like tags
                genre_tags = [t for t in artist_tags if any(x in t.lower() for x in ["rock", "pop", "rap", "dance", "classic", "electronic", "jazz", "metal", "soul", "blues", "folk"])]
                if genre_tags:
                    features_text.append(f"🎸 {genre_tags[0]}")
                    genre_found = True
                    log.info("[GENRE] Last.fm genre for %s: %s", selected_track.artist, genre_tags[0])
        except Exception as e:
            log.warning("[GENRE] Last.fm artist tags failed for %s: %s", selected_track.artist, e)

    # 4. From Last.fm (tags) - show as additional info
    lastfm_tags = target_features.get("lastfm_tags") if isinstance(target_features, dict) else None
    if lastfm_tags:
        features_text.append(f"🏷️ {', '.join(lastfm_tags[:3])}")

    if features_text:
        lines.append("")
        lines.append(f"<blockquote>{' · '.join(features_text)}</blockquote>")

    if selected_track.deezer_url:
        lines.append(f'\n🔊 <a href="{selected_track.deezer_url}">Listen on Deezer</a>')

    lines.append(f'\n📝 Copy to search in @DeezerMusicBot:')
    lines.append(f'<code>{h(selected_track.title)} {h(selected_track.artist)}</code>')

    lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "🎯 <b>Similar Tracks</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━", ""])

    for i, result in enumerate(results[:6], 1):
        score_text = format_similarity_score(result.similarity_score) if result.similarity_score > 0 else ""
        lines.append(f"{i}. <b>{h(result.title)}</b> - {h(result.artist)}")
        if score_text:
            lines.append(f"   {score_text}")
        lines.append(f"   <code>{h(result.title)} {h(result.artist)}</code>")
        lines.append("")

    msg = "\n".join(lines)

    # Split message if too long
    parts = []
    current = ""
    for line in msg.split("\n"):
        if len(current) + len(line) + 1 > 4000:
            if current:
                parts.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        parts.append(current)

    # SEND COMPLETE MESSAGE (with features)
    await query.message.reply_text(msg, parse_mode=PM, disable_web_page_preview=True)

    # Send previews
    _user_state.set(chat_id, {"last_track_title": selected_track.title, "last_track_artist": selected_track.artist})

    for track in top_tracks:
        if track.preview_url:
            try:
                await asyncio.sleep(0.3)
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=track.preview_url,
                    title=f"🎵 {track.title}",
                    performer=track.artist,
                    duration=30,
                )
                vote_msg = f"🎧 <b>{h(track.title)}</b> - {h(track.artist)}\n\n📝 Copy to search in @DeezerMusicBot:\n<code>{h(track.title)} {h(track.artist)}</code>\n\n⭐ Rate this track:"
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=vote_msg,
                    reply_markup=_vote_keyboard(track.id, track.title, track.artist),
                    parse_mode=PM,
                )
            except Exception as e:
                log.error("Failed to send preview for %s: %s", track.title, e)

    _user_state.pop(chat_id, None)


# ═══════════════════════════════════════════════════
# Inline query
# ═══════════════════════════════════════════════════

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    if not query or len(query) < 2:
        return

    search_query = query
    if has_persian(query):
        english = find_persian_english(query)
        if english:
            search_query = english

    try:
        results = await dz.search(search_query, limit=5)
    except Exception:
        return

    articles = []
    for t in results:
        desc = f"{t.album} · {t.bpm_str()}" if t.bpm else t.album
        msg = f"🎵 <b>{h(t.title)}</b>\n👤 {h(t.artist)}\n💿 {h(t.album)}"
        if t.preview_url:
            msg += f'\n\n<a href="{t.preview_url}">🎧 Preview</a>'
        if t.deezer_url:
            msg += f'\n<a href="{t.deezer_url}">▶️ Deezer</a>'
        articles.append(InlineQueryResultArticle(
            id=str(t.id),
            title=f"{t.title} - {t.artist}",
            description=desc,
            thumb_url=t.album_art,
            input_message_content=InputTextMessageContent(msg, parse_mode=PM, disable_web_page_preview=False),
        ))

    await update.inline_query.answer(articles, cache_time=30)


# ═══════════════════════════════════════════════════
# Phase 1: Quick Wins
# ═══════════════════════════════════════════════════

async def cmd_random(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Random song discovery."""
    await update.message.chat.send_action("typing")

    query = " ".join(context.args) if context.args else ""
    search_query = query if query else "popular"

    try:
        results = await dz.search(search_query, limit=20)
        if results:
            track = random.choice(results)
            await add_to_history(update.effective_user.id, track.id, track.title, track.artist, "random")

            msg = f"🎲 <b>Random Discovery!</b>\n\n"
            msg += f"🎵 <b>{h(track.title)}</b>\n"
            msg += f"👤 {h(track.artist)}\n"
            msg += f"💿 {h(track.album)}\n"
            if track.preview_url:
                msg += f'\n<a href="{track.preview_url}">🎧 Preview</a>'
            if track.deezer_url:
                msg += f'\n<a href="{track.deezer_url}">▶️ Deezer</a>'

            await update.message.reply_text(msg, parse_mode=PM, disable_web_page_preview=True)
        else:
            await update.message.reply_text("No random tracks found. Try again!")
    except Exception as e:
        log.error("Random command error: %s", e)
        await update.message.reply_text("Error finding random track. Try again.")


async def cmd_compare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Compare two songs."""
    text = " ".join(context.args) if context.args else ""

    if " vs " not in text and " - " not in text.split("vs")[0] if "vs" in text else True:
        await update.message.reply_text(
            "Usage: /compare Song1 - Artist1 vs Song2 - Artist2\n"
            "Example: /compare Bohemian Rhapsody - Queen vs Stairway to Heaven - Led Zeppelin"
        )
        return

    parts = text.split(" vs ", 1)
    if len(parts) != 2:
        await update.message.reply_text("Please use format: Song1 vs Song2")
        return

    song1, song2 = parts[0].strip(), parts[1].strip()

    # Search for both tracks
    await update.message.chat.send_action("typing")

    try:
        results1 = await dz.search(song1, limit=1)
        results2 = await dz.search(song2, limit=1)

        if not results1 or not results2:
            await update.message.reply_text("Couldn't find one or both tracks. Try more specific names.")
            return

        track1, track2 = results1[0], results2[0]

        # Get features for both
        features1 = await get_cached_features(track1.id)
        features2 = await get_cached_features(track2.id)

        # Build comparison
        msg = f"⚔️ <b>Track Comparison</b>\n\n"
        msg += f"🎵 <b>{h(track1.title)}</b> - {h(track1.artist)}\n"
        msg += f"   vs\n"
        msg += f"🎵 <b>{h(track2.title)}</b> - {h(track2.artist)}\n\n"

        # Feature comparison
        msg += "━━━ <b>Features</b> ━━━\n"

        if features1 and features2:
            af1 = features1.get("audio_features")
            af2 = features2.get("audio_features")

            if af1 and af2:
                msg += f"🥁 BPM: {af1.bpm:.0f} vs {af2.bpm:.0f}\n"
                msg += f"⚡ Energy: {af1.rms_energy:.2f} vs {af2.rms_energy:.2f}\n"

            ac1 = features1.get("acoustic_features")
            ac2 = features2.get("acoustic_features")

            if ac1 and ac2:
                msg += f"😊 Valence: {ac1.valence:.2f} vs {ac2.valence:.2f}\n"
                msg += f"💃 Dance: {ac1.danceability:.2f} vs {ac2.danceability:.2f}\n"
        else:
            msg += "Features not available for one or both tracks.\n"

        await update.message.reply_text(msg, parse_mode=PM)

    except Exception as e:
        log.error("Compare command error: %s", e)
        await update.message.reply_text("Error comparing tracks. Try again.")


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's listening history."""
    user_id = update.effective_user.id

    history = await get_user_history(user_id, limit=15)

    if not history:
        await update.message.reply_text(
            "📜 <b>Your History</b>\n\n"
            "No history yet! Start searching for songs.",
            parse_mode=PM
        )
        return

    msg = "📜 <b>Your Recent Activity</b>\n\n"

    for title, artist, action, created_at in history:
        action_emoji = {"search": "🔍", "random": "🎲", "trivia": "🎮"}.get(action, "🎵")
        msg += f"{action_emoji} <b>{h(title)}</b> - {h(artist)}\n"

    await update.message.reply_text(msg, parse_mode=PM)


async def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show ranked similar tracks."""
    query = " ".join(context.args) if context.args else ""

    if not query:
        await update.message.reply_text("Usage: /chart Song Name Artist")
        return

    await update.message.chat.send_action("typing")

    try:
        results = await dz.search(query, limit=1)
        if not results:
            await update.message.reply_text("Track not found. Try a different search.")
            return

        track = results[0]

        # Get similar tracks
        similar = await dz.get_similar(track.id, limit=10)

        if not similar:
            await update.message.reply_text("No similar tracks found.")
            return

        msg = f"📊 <b>Chart: Similar to {h(track.title)}</b>\n"
        msg += f"👤 {h(track.artist)}\n\n"

        for i, s in enumerate(similar[:10], 1):
            msg += f"{i}. <b>{h(s.title)}</b> - {h(s.artist)}\n"

        await update.message.reply_text(msg, parse_mode=PM)

    except Exception as e:
        log.error("Chart command error: %s", e)
        await update.message.reply_text("Error generating chart. Try again.")


# ═══════════════════════════════════════════════════
# Phase 2: Mood & Activity
# ═══════════════════════════════════════════════════

async def cmd_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mood-based recommendations."""
    mood = context.args[0].lower() if context.args else ""

    mood_queries = {
        "happy": "happy upbeat",
        "chill": "chill relaxed",
        "workout": "workout energy",
        "sad": "sad emotional",
        "party": "party dance",
        "focus": "focus study",
        "sleep": "sleep calm",
        "romantic": "romantic love",
    }

    if not mood or mood not in mood_queries:
        msg = "🎵 <b>Mood Playlists</b>\n\n"
        msg += "Available moods:\n"
        for m in mood_queries:
            msg += f"  • /mood {m}\n"
        await update.message.reply_text(msg, parse_mode=PM)
        return

    await update.message.chat.send_action("typing")

    try:
        results = await dz.search(mood_queries[mood], limit=10)
        if results:
            msg = f"🎵 <b>{mood.capitalize()} Playlist</b>\n\n"
            for i, track in enumerate(results[:8], 1):
                msg += f"{i}. <b>{h(track.title)}</b> - {h(track.artist)}\n"

            await update.message.reply_text(msg, parse_mode=PM)
        else:
            await update.message.reply_text("No tracks found for this mood.")
    except Exception as e:
        log.error("Mood command error: %s", e)
        await update.message.reply_text("Error finding mood tracks.")


async def cmd_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activity-based playlists."""
    activity = context.args[0].lower() if context.args else ""

    activity_queries = {
        "running": "running workout high energy",
        "studying": "study focus ambient",
        "sleeping": "sleep ambient calm",
        "cooking": "cooking feel good",
        "gaming": "gaming electronic",
        "driving": "driving road trip",
        "coding": "coding focus electronic",
    }

    if not activity or activity not in activity_queries:
        msg = "🏃 <b>Activity Playlists</b>\n\n"
        msg += "Available activities:\n"
        for a in activity_queries:
            msg += f"  • /activity {a}\n"
        await update.message.reply_text(msg, parse_mode=PM)
        return

    await update.message.chat.send_action("typing")

    try:
        results = await dz.search(activity_queries[activity], limit=10)
        if results:
            msg = f"🏃 <b>{activity.capitalize()} Playlist</b>\n\n"
            for i, track in enumerate(results[:8], 1):
                msg += f"{i}. <b>{h(track.title)}</b> - {h(track.artist)}\n"

            await update.message.reply_text(msg, parse_mode=PM)
        else:
            await update.message.reply_text("No tracks found for this activity.")
    except Exception as e:
        log.error("Activity command error: %s", e)
        await update.message.reply_text("Error finding activity tracks.")


# ═══════════════════════════════════════════════════
# Phase 3: Playlists
# ═══════════════════════════════════════════════════

async def cmd_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a playlist from a seed track."""
    query = " ".join(context.args) if context.args else ""

    if not query:
        await update.message.reply_text("Usage: /playlist Song Name Artist")
        return

    await update.message.chat.send_action("typing")

    try:
        results = await dz.search(query, limit=1)
        if not results:
            await update.message.reply_text("Track not found.")
            return

        track = results[0]

        # Get similar tracks
        similar = await dz.get_similar(track.id, limit=10)

        # Build playlist
        seed = {
            "track_id": track.id,
            "title": track.title,
            "artist": track.artist,
            "energy": 0.5,
            "bpm": track.bpm or 120,
            "preview_url": track.preview_url or "",
        }

        similar_list = []
        for s in similar[:9]:
            similar_list.append({
                "track_id": s.id,
                "title": s.title,
                "artist": s.artist,
                "energy": 0.5,
                "bpm": s.bpm or 120,
                "preview_url": s.preview_url or "",
            })

        playlist = await generate_playlist(seed, similar_list, max_tracks=10)

        # Save playlist
        user_id = update.effective_user.id
        name = f"Similar to {track.title}"
        track_ids = [t.track_id for t in playlist]
        playlist_id = await save_playlist(user_id, name, track_ids)

        # Format and send
        msg = format_playlist_text(playlist, name)
        msg += f"\n💾 Saved as playlist #{playlist_id}"

        await update.message.reply_text(msg, parse_mode=PM)

    except Exception as e:
        log.error("Playlist command error: %s", e)
        await update.message.reply_text("Error generating playlist.")


async def cmd_playlists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List user's saved playlists."""
    user_id = update.effective_user.id

    playlists = await get_user_playlists(user_id)

    if not playlists:
        await update.message.reply_text(
            "📁 <b>Your Playlists</b>\n\n"
            "No playlists saved yet!\n"
            "Use /playlist to create one.",
            parse_mode=PM
        )
        return

    msg = "📁 <b>Your Playlists</b>\n\n"
    for p in playlists:
        msg += f"#{p['id']} <b>{h(p['name'])}</b> ({len(p['track_ids'])} tracks)\n"

    await update.message.reply_text(msg, parse_mode=PM)


# ═══════════════════════════════════════════════════
# Phase 4: Taste Profile
# ═══════════════════════════════════════════════════

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's taste profile."""
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "User"

    # Get user's votes
    votes_raw = await get_user_votes(user_id, limit=50)

    if not votes_raw:
        await update.message.reply_text(
            "🎵 <b>Your Taste Profile</b>\n\n"
            "No ratings yet! Rate some songs first.",
            parse_mode=PM
        )
        return

    # Get rating stats
    stats = await get_user_rating_stats(user_id)

    # Build taste profile
    votes = []
    for title, artist, rating in votes_raw:
        votes.append({"rating": rating})

    profile = build_taste_profile(votes, {})
    profile.total_ratings = stats["total_votes"]
    profile.avg_rating = stats["avg_rating"]

    # Get top artists
    top_artists = await get_user_top_artists(user_id, limit=5)
    if top_artists:
        profile.top_artists = [a[0] for a in top_artists]

    # Format and send
    msg = format_taste_profile(profile, username)

    if profile.top_artists:
        msg += "━━━ <b>Top Artists</b> ━━━\n"
        for artist in profile.top_artists:
            msg += f"🎤 {h(artist)}\n"

    await update.message.reply_text(msg, parse_mode=PM)


async def cmd_recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Personalized recommendations based on taste."""
    user_id = update.effective_user.id

    votes_raw = await get_user_votes(user_id, limit=20)

    if not votes_raw:
        await update.message.reply_text(
            "No taste data yet! Rate some songs first.",
            parse_mode=PM
        )
        return

    await update.message.chat.send_action("typing")

    try:
        # Get a random track from user's history to base recommendations on
        if votes_raw:
            title, artist, _ = random.choice(votes_raw)
            results = await dz.search(f"{title} {artist}", limit=1)

            if results:
                track = results[0]
                similar = await dz.get_similar(track.id, limit=10)

                if similar:
                    msg = f"💡 <b>Based on your taste</b>\n\n"
                    msg += f"Because you liked <b>{h(title)}</b>:\n\n"

                    for i, s in enumerate(similar[:8], 1):
                        msg += f"{i}. <b>{h(s.title)}</b> - {h(s.artist)}\n"

                    await update.message.reply_text(msg, parse_mode=PM)
                else:
                    await update.message.reply_text("No recommendations found.")
            else:
                await update.message.reply_text("Could not find recommendations.")
        else:
            await update.message.reply_text("No taste data available.")

    except Exception as e:
        log.error("Recommend command error: %s", e)
        await update.message.reply_text("Error generating recommendations.")


# ═══════════════════════════════════════════════════
# Phase 5: Trivia
# ═══════════════════════════════════════════════════

async def cmd_trivia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a music trivia game."""
    user_id = update.effective_user.id

    # Check for subcommands
    if context.args and context.args[0] == "leaderboard":
        return await cmd_trivia_leaderboard(update, context)

    if context.args and context.args[0] == "stats":
        stats = await get_trivia_stats(user_id)
        msg = format_session_stats(TriviaSession(user_id=user_id, score=stats["score"], questions_asked=stats["games"]))
        await update.message.reply_text(msg, parse_mode=PM)
        return

    # Start new game
    session = start_session(user_id)

    # Get random tracks for options
    try:
        results = await dz.search("popular", limit=20)
        if not results:
            await update.message.reply_text("Error starting trivia. Try again.")
            return

        # Pick a random track
        correct_track = random.choice(results)
        all_tracks = [{"title": t.title, "artist": t.artist} for t in results]

        # Create question
        question = create_trivia_question(
            {
                "track_id": correct_track.id,
                "title": correct_track.title,
                "artist": correct_track.artist,
                "preview_url": correct_track.preview_url,
            },
            all_tracks
        )

        session.current_question = question

        # Send audio preview
        if correct_track.preview_url:
            await context.bot.send_audio(
                chat_id=update.effective_chat.id,
                audio=correct_track.preview_url,
                title="🎵 Trivia Clue",
                duration=30,
            )

        # Send question
        msg = format_question(question)
        await update.message.reply_text(msg, parse_mode=PM)

    except Exception as e:
        log.error("Trivia command error: %s", e)
        await update.message.reply_text("Error starting trivia. Try again.")


async def cmd_trivia_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show trivia leaderboard."""
    leaderboard = await get_trivia_leaderboard(limit=10)

    if not leaderboard:
        await update.message.reply_text("No trivia scores yet! Be the first to play.")
        return

    msg = "🏆 <b>Trivia Leaderboard</b>\n\n"

    medals = ["🥇", "🥈", "🥉"]
    for i, (username, score, games, streak) in enumerate(leaderboard):
        medal = medals[i] if i < 3 else f"{i+1}."
        msg += f"{medal} <b>{h(username)}</b> - {score} pts ({games} games)\n"

    await update.message.reply_text(msg, parse_mode=PM)


async def handle_trivia_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle trivia answer (number 1-4)."""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    session = get_session(user_id)
    if not session or not session.current_question:
        return False  # Not a trivia answer

    if text not in ["1", "2", "3", "4"]:
        return False

    answer_index = int(text) - 1
    is_correct, message = check_answer(session, answer_index)

    if is_correct:
        await update_trivia_score(user_id, update.effective_user.first_name, 10, True)
    else:
        await update_trivia_score(user_id, update.effective_user.first_name, 0, False)

    await update.message.reply_text(message, parse_mode=PM)

    # If question was answered (correct or out of attempts), ask next
    if session.current_question is None and session.questions_asked < 5:
        # Wait a moment then ask next
        await asyncio.sleep(1)
        # Get new question
        try:
            results = await dz.search("popular", limit=20)
            if results:
                correct_track = random.choice(results)
                all_tracks = [{"title": t.title, "artist": t.artist} for t in results]

                question = create_trivia_question(
                    {
                        "track_id": correct_track.id,
                        "title": correct_track.title,
                        "artist": correct_track.artist,
                        "preview_url": correct_track.preview_url,
                    },
                    all_tracks
                )

                session.current_question = question

                if correct_track.preview_url:
                    await context.bot.send_audio(
                        chat_id=update.effective_chat.id,
                        audio=correct_track.preview_url,
                        title="🎵 Next Song",
                        duration=30,
                    )

                msg = format_question(question)
                await update.message.reply_text(msg, parse_mode=PM)
        except Exception:
            pass
    elif session.questions_asked >= 5:
        # Game over
        msg = f"🎮 <b>Game Over!</b>\n\nFinal score: {session.score}\n"
        await update.message.reply_text(msg, parse_mode=PM)
        end_session(user_id)

    return True


# ═══════════════════════════════════════════════════
# Phase 6: Lyrics
# ═══════════════════════════════════════════════════

async def cmd_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get lyrics for a song."""
    query = " ".join(context.args) if context.args else ""

    if not query:
        await update.message.reply_text("Usage: /lyrics Song Name Artist")
        return

    await update.message.chat.send_action("typing")

    lyrics_client = LyricsClient()

    try:
        # Try to parse artist - title format
        if " - " in query:
            parts = query.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()
        else:
            # Search for the track first
            results = await dz.search(query, limit=1)
            if results:
                artist = results[0].artist
                title = results[0].title
            else:
                await update.message.reply_text("Track not found.")
                return

        result = await lyrics_client.get_lyrics(artist, title)

        if result and result.lyrics:
            msg = format_lyrics(result)
            await update.message.reply_text(msg, parse_mode=PM)
        else:
            await update.message.reply_text(f"No lyrics found for {title} - {artist}")

    except Exception as e:
        log.error("Lyrics command error: %s", e)
        await update.message.reply_text("Error fetching lyrics.")
    finally:
        await lyrics_client.close()


async def cmd_searchlyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search for songs by lyrics."""
    query = " ".join(context.args) if context.args else ""

    if not query:
        await update.message.reply_text("Usage: /searchlyrics lyrics text")
        return

    await update.message.chat.send_action("typing")

    lyrics_client = LyricsClient()

    try:
        results = await lyrics_client.search_lyrics(query, limit=5)

        if results:
            msg = f"🔍 <b>Lyrics Search Results</b>\n\n"
            for r in results:
                msg += f"🎵 <b>{h(r.title)}</b> - {h(r.artist)}\n"

            await update.message.reply_text(msg, parse_mode=PM)
        else:
            await update.message.reply_text("No lyrics found matching your search.")

    except Exception as e:
        log.error("Search lyrics error: %s", e)
        await update.message.reply_text("Error searching lyrics.")
    finally:
        await lyrics_client.close()


# ═══════════════════════════════════════════════════
# Phase 7: Share & Social
# ═══════════════════════════════════════════════════

async def cmd_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a shareable music card."""
    query = " ".join(context.args) if context.args else ""

    if not query:
        await update.message.reply_text("Usage: /share Song Name Artist")
        return

    await update.message.chat.send_action("typing")

    try:
        results = await dz.search(query, limit=1)
        if not results:
            await update.message.reply_text("Track not found.")
            return

        track = results[0]
        features = await get_cached_features(track.id)

        # Get feature values
        bpm = track.bpm or 0
        energy = 0.5
        valence = 0.5
        danceability = 0.5

        if features:
            af = features.get("audio_features")
            ac = features.get("acoustic_features")
            if af:
                bpm = af.bpm
                energy = af.rms_energy
            if ac:
                valence = ac.valence
                danceability = ac.danceability

        # Generate card image
        card_bytes = generate_music_card(
            title=track.title,
            artist=track.artist,
            bpm=bpm,
            energy=energy,
            valence=valence,
            danceability=danceability,
        )

        if card_bytes:
            await update.message.reply_photo(
                photo=card_bytes,
                caption=f"🎵 {track.title} - {track.artist}\n\nGenerated by Music Suggest Bot",
            )
        else:
            # Fallback to text
            msg = f"🎵 <b>{h(track.title)}</b>\n👤 {h(track.artist)}\n\n"
            msg += f"BPM: {bpm:.0f} | Energy: {energy:.2f} | Valence: {valence:.2f}"
            await update.message.reply_text(msg, parse_mode=PM)

    except Exception as e:
        log.error("Share command error: %s", e)
        await update.message.reply_text("Error generating card.")


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show global leaderboard."""
    top_tracks = await get_top_rated_tracks(limit=10)
    top_users = await get_most_active_users(limit=5)

    msg = "🏆 <b>Global Stats</b>\n\n"

    if top_tracks:
        msg += "━━━ <b>Top Rated Tracks</b> ━━━\n"
        for i, (title, artist, avg_rating, votes) in enumerate(top_tracks, 1):
            stars = "⭐" * int(avg_rating)
            msg += f"{i}. <b>{h(title)}</b> - {h(artist)}\n"
            msg += f"   {stars} ({votes} votes)\n"
        msg += "\n"

    if top_users:
        msg += "━━━ <b>Most Active Users</b> ━━━\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, (user_id, votes, avg_rating) in enumerate(top_users):
            medal = medals[i] if i < 3 else f"{i+1}."
            msg += f"{medal} User {user_id} - {votes} ratings\n"

    await update.message.reply_text(msg, parse_mode=PM)


# ═══════════════════════════════════════════════════
# Phase 8: Musical DNA
# ═══════════════════════════════════════════════════

async def cmd_dna(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate musical DNA visualization."""
    query = " ".join(context.args) if context.args else ""

    if not query:
        await update.message.reply_text("Usage: /dna Song Name Artist")
        return

    await update.message.chat.send_action("typing")

    try:
        results = await dz.search(query, limit=1)
        if not results:
            await update.message.reply_text("Track not found.")
            return

        track = results[0]
        features = await get_cached_features(track.id)

        # Get feature values
        bpm = track.bpm or 0
        energy = 0.5
        valence = 0.5
        danceability = 0.5
        mfcc_means = []
        chroma_means = []

        if features:
            af = features.get("audio_features")
            ac = features.get("acoustic_features")
            if af:
                bpm = af.bpm
                energy = af.rms_energy
                mfcc_means = af.mfcc_mean
                chroma_means = af.chroma_mean
            if ac:
                valence = ac.valence
                danceability = ac.danceability

        # Generate DNA image
        dna_bytes = generate_musical_dna(
            title=track.title,
            artist=track.artist,
            bpm=bpm,
            energy=energy,
            valence=valence,
            danceability=danceability,
            mfcc_means=mfcc_means,
            chroma_means=chroma_means,
        )

        if dna_bytes:
            await update.message.reply_photo(
                photo=dna_bytes,
                caption=f"🧬 Musical DNA: {track.title} - {track.artist}\n\nEach song has a unique fingerprint!",
            )
        else:
            await update.message.reply_text("Error generating DNA visualization.")

    except Exception as e:
        log.error("DNA command error: %s", e)
        await update.message.reply_text("Error generating DNA.")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all available commands."""
    msg = """
🎵 <b>Music Suggest Bot v3</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🔍 Discovery</b>
  /search <i>Song Name</i> - Search for songs
  /random [genre] - Random discovery
  /chart <i>Song Artist</i> - Similar tracks

<b>🎯 Recommendations</b>
  /mood - happy, chill, workout, sad, party
  /activity - running, studying, gaming
  /playlist - Generate playlist

<b>📊 Analysis</b>
  /compare <i>Song1 vs Song2</i> - Compare songs
  /dna <i>Song Artist</i> - Musical DNA
  /share <i>Song Artist</i> - Share card

<b>👤 Personal</b>
  /profile - Your taste profile
  /recommend - Get recommendations
  /history - Your history

<b>🎮 Fun</b>
  /trivia - Play trivia game
  /top - Global leaderboard

<b>🎤 Lyrics</b>
  /lyrics <i>Song Artist</i> - Get lyrics

<b>📋 My Playlist</b>
  /add <i>Song Artist</i> - Add to playlist
  /done - Finish adding songs
  /myplaylist - View playlist
  /clearplaylist - Clear playlist
  /meforyou - Get songs matching your taste
  /playliststats - See your taste stats
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(msg, parse_mode=PM)


# ═══════════════════════════════════════════════════
# Genre extraction helper
# ═══════════════════════════════════════════════════

# Actual genre words (not year/artist/mood tags like "80s", "Queen", "british")
_GENRE_WORDS = {
    "rock", "pop", "metal", "jazz", "blues", "soul", "funk", "reggae",
    "classical", "electronic", "dance", "hip hop", "rap", "country",
    "folk", "indie", "punk", "grunge", "alternative", "classic rock",
    "hard rock", "heavy metal", "progressive", "psychedelic", "r&b",
    "rnb", "disco", "house", "techno", "trance", "ambient", "trip hop",
    "dubstep", "drum and bass", "latin", "salsa", "tango", "flamenco",
    "gospel", "opera", "soundtrack", "score", "world", "traditional",
    "persian traditional", "iranian", "pop rock", "soft rock", "new wave",
    "synthpop", "synth pop", "art rock", "garage rock", "blues rock",
    "folk rock", "southern rock", "country rock", "singer-songwriter",
    "vocal", "acoustic", "instrumental", "chill", "lo-fi", "lofi",
    "phonk", "drill", "trap", "grime", "afrobeat", "highlife", "morna",
    "fado", "celtic", "k-pop", "j-pop", "c-pop", "bollywood", "filmi",
    "qawwali", "sufi", "ghazal", "taraneh", "pop persian", "dance pop",
    "electropop", "synthwave", "vaporwave", "shoegaze", "dream pop",
    "britpop", "madchester", "post-punk", "industrial", "ebm",
    "christmas", "children's", "spoken word", "comedy",
}

# Tags that are NOT genres — skip them when picking a genre from Last.fm
_NON_GENRE_TAGS = {
    "80s", "90s", "70s", "60s", "50s", "00s", "2010s", "2000s",
    "queen", "beatles", "classic", "oldies", "greatest hits", "live",
    "british", "american", "irish", "australian", "canadian",
    "male vocalists", "female vocalists", "seen live", "favorites",
    "chill", "mellow", "happy", "sad", "romantic", "party", "summer",
}


def _extract_genre_from_tags(tags: list) -> str:
    """Pick the first actual genre from a list of Last.fm-style tags."""
    if not tags:
        return ""
    for t in tags:
        tl = t.strip().lower()
        if tl in _NON_GENRE_TAGS:
            continue
        # Direct genre word match
        if tl in _GENRE_WORDS:
            return t.strip()
    # Fuzzy: tag contains a genre word (e.g. "classic rock", "persian traditional")
    for t in tags:
        tl = t.strip().lower()
        for word in _GENRE_WORDS:
            if word in tl:
                return t.strip()
    # No real genre found — return empty rather than a year/artist/mood tag
    return ""


async def _extract_genre(track, features) -> str:
    """Get the genre for a track from: Persian DB -> Deezer -> Last.fm tags."""
    # 1. Persian genre database (most accurate for Persian artists)
    if track.artist in PERSIAN_GENRES:
        return PERSIAN_GENRES[track.artist][0]
    if has_persian(track.artist) or has_persian(track.title):
        for artist_name, genres in PERSIAN_GENRES.items():
            if artist_name.lower() in track.artist.lower():
                return genres[0]
    # 2. Track-level genres from Deezer
    if getattr(track, "genres", None):
        return track.genres[0]
    # 3. Last.fm tags (pick an actual genre word)
    if features and isinstance(features, dict):
        tags = features.get("lastfm_tags") or []
        genre = _extract_genre_from_tags(tags)
        if genre:
            return genre
    return ""


# ═══════════════════════════════════════════════════
# Playlist Add / Done
# ═══════════════════════════════════════════════════

# ═══════════════════════════════════════════════════
# Language
# ═══════════════════════════════════════════════════

async def _show_language_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show a picker to choose the bot's language."""
    buttons = []
    for code, name in supported_langs().items():
        buttons.append([InlineKeyboardButton(name, callback_data=f"lang_{code}")])
    await update.message.reply_text(
        "🌐 <b>Choose your language / زبان خود را انتخاب کنید:</b>",
        parse_mode=PM,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_language_picker(update, context)


# ═══════════════════════════════════════════════════
# Playlist commands
# ═══════════════════════════════════════════════════

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a song to user's playlist."""
    user_id = update.effective_user.id
    query = " ".join(context.args) if context.args else update.message.text.strip()

    if not query or query.startswith("✅") or query.startswith("❌"):
        return

    await update.message.chat.send_action("typing")

    # Clean up query
    search_query = query.replace("-", " ").replace("_", " ")
    search_query = re.sub(r'\.(mp3|wav|flac|m4a|ogg|wma)$', '', search_query, flags=re.IGNORECASE)
    search_query = re.sub(r'[\s]*[-_]?\s*\d+\s*$', '', search_query)
    search_query = ' '.join(search_query.split())

    # Search Deezer - automatically pick best match
    try:
        results = await dz.search(search_query, limit=3)
        if not results:
            _failed_songs.setdefault(user_id, []).append(query)
            count = len(_pending_songs.get(user_id, []))
            await update.message.reply_text(
                f"❌ Not found: <code>{h(query)}</code>",
                parse_mode=PM,
                reply_markup=_playlist_mode_keyboard(count),
            )
            return

        # Pick the first (most popular) result
        track = results[0]

        # Release year for era stats
        release_year = 0
        try:
            full_track = await dz.get_track(track.id)
            if full_track:
                release_year = full_track.release_year()
                if full_track.bpm and not track.bpm:
                    track.bpm = full_track.bpm
        except Exception:
            pass

        # Language detection
        is_persian = has_persian(query) or has_persian(track.title) or has_persian(track.artist)
        lang = detect_language(track.title, track.artist, query)

        # Find 5 similar tracks and store them in the per-user suggestion pool
        similar_ids = []
        try:
            similar_tracks = await dz.get_similar(track.id, limit=5)
            similar_ids = [t.id for t in similar_tracks]
        except Exception as e:
            log.warning("cmd_add: get_similar failed for %s: %s", track.id, e)
        try:
            await store_suggestions(user_id, track.id, similar_ids)
        except Exception as e:
            log.warning("cmd_add: store_suggestions failed user=%s: %s", user_id, e)

        # Analyze features
        features = await analyze_track(track, fast_mode=True)
        bpm = features.get("audio_features").bpm if features.get("audio_features") else 0
        energy = features.get("audio_features").rms_energy if features.get("audio_features") else 0
        valence = features.get("acoustic_features").valence if features.get("acoustic_features") else 0

        # Add to playlist
        await add_to_user_playlist(
            user_id,
            track.id,
            track.title,
            track.artist,
            bpm,
            energy,
            valence,
            language=lang,
            recognized=True,
            release_year=release_year,
        )

        # Update count
        count = len(_pending_songs.get(user_id, []))

        await update.message.reply_text(
            f"✅ <b>{h(track.title)}</b> - {h(track.artist)}",
            parse_mode=PM,
            reply_markup=_playlist_mode_keyboard(count),
        )

    except Exception as e:
        log.error("Add to playlist error: %s", e)
        _failed_songs.setdefault(user_id, []).append(query)


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish adding songs and process all at once with progress bar."""
    user_id = update.effective_user.id
    log_step(4, user_id, "Starting processing")
    _playlist_mode[user_id] = False

    # Get pending songs
    pending = _pending_songs.pop(user_id, [])
    log_step(4, user_id, f"Got {len(pending)} pending songs")

    if not pending:
        log_step(4, user_id, "No songs to process")
        await update.message.reply_text(
            "❌ No songs to process.",
            reply_markup=_main_menu_keyboard(),
        )
        return

    # Parse all songs from pending list (handle multiline)
    all_songs = []
    for item in pending:
        lines = item.split('\n')
        for line in lines:
            line = line.strip()
            if line:
                all_songs.append(line)
    log_step(4, user_id, f"Parsed {len(all_songs)} songs from input")

    # Clean song names
    cleaned_songs = []
    for song in all_songs:
        cleaned = clean_song_name(song)
        if cleaned:
            cleaned_songs.append({"original": song, "cleaned": cleaned})
    log_step(5, user_id, f"Cleaned {len(cleaned_songs)} songs")

    if not cleaned_songs:
        log_step(5, user_id, "No valid songs after cleaning")
        await update.message.reply_text(
            "❌ No valid songs to process.",
            reply_markup=_main_menu_keyboard(),
        )
        return

    # Show initial message
    total = len(cleaned_songs)
    chat_id = update.effective_chat.id
    progress_msg = await update.message.reply_text(
        f"⏳ <b>Processing {total} songs...</b>\n"
        f"This may take a while. I'll notify you when done!",
        parse_mode=PM,
    )

    # Process all songs
    added_count = 0
    recognized_count = 0
    failed = []

    for i, song_info in enumerate(cleaned_songs):
        original = song_info["original"]
        cleaned = song_info["cleaned"]
        log_step(6, user_id, f"Processing {i+1}/{total}: '{original}' -> '{cleaned}'")

        # Update progress
        progress = int((i + 1) / total * 10)
        bar = "█" * progress + "░" * (10 - progress)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text=f"⏳ <b>Processing songs...</b>\n\n"
                     f"<code>[{bar}]</code> {i + 1}/{total}\n"
                     f"Current: {h(cleaned[:30])}...",
                parse_mode=PM,
            )
        except Exception as e:
            log_step(6, user_id, f"Progress update failed: {e}")

        # Search Deezer
        try:
            log_step(6, user_id, f"Searching Deezer for: {cleaned}")
            results = await dz.search(cleaned, limit=3)
            if not results:
                log_step(6, user_id, f"No results for: {cleaned}")

                # Still add the song to the playlist (so the user's full list is
                # saved), but as UNRECOGNIZED — excluded from taste analysis and
                # similar-track pooling.
                lang = detect_language("", "", original)
                await add_to_user_playlist(
                    user_id,
                    0,
                    cleaned,
                    "",
                    original_text=original,
                    language=lang,
                    recognized=False,
                )
                failed.append(original)
                continue

            # Pick the most famous result
            track = results[0]
            log_step(6, user_id, f"Found: {track.title} - {track.artist}")

            # Get full track (release_year for era; genres sometimes here)
            release_year = 0
            try:
                full_track = await dz.get_track(track.id)
                if full_track:
                    release_year = full_track.release_year()
                    # Prefer full-track metadata if it has a better bpm
                    if full_track.bpm and not track.bpm:
                        track.bpm = full_track.bpm
            except Exception:
                pass

            # Check if Persian / detect language
            is_persian = has_persian(original) or has_persian(track.title) or has_persian(track.artist)
            lang = detect_language(track.title, track.artist, original)
            log_step(6, user_id, f"Language: {lang} (persian={is_persian})")

            # Analyze features (full analysis - takes 10-12 seconds but gives real data)
            log_step(6, user_id, "Analyzing features (librosa)...")
            try:
                features = await analyze_track(track, fast_mode=False)
                if features and isinstance(features, dict) and features.get("audio_features"):
                    log_step(6, user_id, f"Features OK: BPM={features['audio_features'].bpm}")
                else:
                    log_step(6, user_id, "Features analyzed (no audio data)")
            except Exception as e:
                log_step(6, user_id, f"Feature analysis failed: {e}")
                features = None

            bpm = 0
            energy = 0
            valence = 0
            genre = ""

            if features and isinstance(features, dict):
                if features.get("audio_features"):
                    bpm = features["audio_features"].bpm or 0
                    energy = features["audio_features"].rms_energy or 0
                if features.get("acoustic_features"):
                    valence = features["acoustic_features"].valence or 0

            # Get genre from Persian database or Last.fm
            genre = await _extract_genre(track, features)

            # Find 5 similar tracks
            similar_ids = []
            try:
                similar_tracks = await dz.get_similar(track.id, limit=5)
                similar_ids = [t.id for t in similar_tracks]
            except Exception:
                pass

            # Store the similar-track IDs in the per-user suggestion pool so
            # "For Me" can sample from them later (one row per suggestion).
            try:
                await store_suggestions(user_id, track.id, similar_ids)
            except Exception as e:
                log.warning("[PLAYLIST_DB] store_suggestions failed user=%s: %s", user_id, e)

            # Add to playlist
            await add_to_user_playlist(
                user_id,
                track.id,
                track.title,
                track.artist,
                bpm,
                energy,
                valence,
                genre,
                is_persian,
                similar_ids,
                original,
                language=lang,
                recognized=True,
                release_year=release_year,
            )
            added_count += 1
            recognized_count += 1
            log_step(7, user_id, f"Added: {track.title} - {track.artist} (genre: {genre}) lang={lang} year={release_year}")

        except Exception as e:
            log_step(6, user_id, f"Error: {e}")
            failed.append(original)

    # Step 7: Show final results
    log_step(7, user_id, f"Processing complete: {added_count}/{total} added, {recognized_count} recognized, {len(failed)} failed")

    # Get taste profile
    profile = await get_user_taste_profile(user_id)
    log_step(9, user_id, f"Taste profile: {profile['track_count']} tracks, genres: {profile.get('genres', {})}")

    # Build final message
    msg = f"✅ <b>Playlist Saved!</b>\n\n"
    msg += f"📊 <b>Summary:</b>\n"
    msg += f"🎵 {added_count}/{total} songs added\n"
    msg += f"✅ {recognized_count} songs recognized\n\n"

    # Taste profile (show if 5+ songs)
    if profile["track_count"] >= 5:
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🎯 <b>Your Taste Profile:</b>\n"
        msg += f"🎵 {profile['track_count']} songs in playlist\n"
        msg += f"🥁 Avg BPM: {profile['avg_bpm']:.0f}\n"
        msg += f"⚡ Avg Energy: {profile['avg_energy']:.2f}\n"
        msg += f"😊 Avg Valence: {profile['avg_valence']:.2f}\n\n"

        # Language stats (all languages, percentages)
        languages = profile.get("languages") or {}
        if languages:
            recog_total = profile.get("recognized_count") or sum(languages.values())
            msg += "🌍 <b>Languages:</b>\n"
            for lang_code, count in sorted(languages.items(), key=lambda x: x[1], reverse=True)[:5]:
                name, flag = language_label(lang_code)
                pct = (count / recog_total * 100) if recog_total else 0
                msg += f"  {flag} {name}: {count} ({pct:.0f}%)\n"
        msg += "\n"

        # Genre stats
        if profile.get("genres"):
            msg += "🎸 <b>Genres:</b>\n"
            for genre, count in list(profile['genres'].items())[:5]:
                msg += f"  • {h(genre)}: {count}\n"

    # Show failed songs if any
    if failed:
        msg += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"⚠️ <b>Not Recognized ({len(failed)}):</b>\n"
        for song in failed[:5]:
            msg += f"  • {h(song)}\n"
        if len(failed) > 5:
            msg += f"  • ... and {len(failed) - 5} more\n"

    msg += f"\nTap <b>🎯 For Me</b> to get songs matching your taste!"

    log_step(8, user_id, "Saving playlist to database")
    # Playlist is already saved in the loop above

    # Send final results
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode=PM,
            reply_markup=_main_menu_keyboard(),
        )
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=progress_msg.message_id,
        )
        log_step(8, user_id, "Results sent successfully")
    except Exception as e:
        log_step(8, user_id, f"Error sending results: {e}")


async def cmd_myplaylist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's playlist with stats and explain its purpose."""
    user_id = update.effective_user.id
    playlist = await get_user_playlist(user_id)

    # 'total_count' from the DB + taste profile for stats
    profile = await get_user_taste_profile(user_id)

    msg = (
        "🎯 <b>Your Music Playlist</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📖 <b>How this works:</b>\n"
        "This playlist is your personal <b>taste fingerprint</b>. Each song you add is "
        "analyzed in the background (BPM, energy, genre, language, era) and we save the "
        "<b>5 most similar songs</b> we find for it. Every time you tap <b>🎯 For Me</b>, "
        "we recommend new songs matched to what you've collected here. "
        "The more you add, the smarter your recommendations get.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    if not playlist:
        msg += "Empty! Tap <b>➕ Add to Playlist</b> to start building your taste profile."
        await update.message.reply_text(msg, parse_mode=PM, reply_markup=_main_menu_keyboard())
        return

    # Song list (first 10)
    msg += "<b>Your Songs:</b>\n"
    for i, row in enumerate(playlist[:10], 1):
        # row: id, original_text, track_id, title, artist, bpm, energy, valence,
        #      genre, is_persian, similar_tracks, language, recognized, release_year, added_at
        (_, _, track_id, title, artist, bpm, energy, valence, genre,
         is_persian, similar_tracks, language, recognized, release_year, _) = row
        title = title or "(unrecognized)"
        line = f"{i}. <b>{h(title)}</b>"
        if artist:
            line += f" - {h(artist)}"
        line += "\n"
        if not recognized:
            line += f"   ⚠️ Not recognized — saved, not used in analysis\n"
        elif bpm > 0:
            line += f"   🥁 {bpm:.0f} BPM"
            if genre:
                line += f" · 🎸 {h(genre)}"
            if release_year:
                line += f" · 📅 {release_year}"
            line += "\n"
        msg += line

    if len(playlist) > 10:
        msg += f"\n... and {len(playlist) - 10} more songs\n"

    # ─── Stats section ───
    msg += "\n📊 <b>Your Stats:</b>\n"

    # Total
    total = profile.get("total_count") or len(playlist)
    msg += f"🎵 Total: {total} songs\n"

    # Language breakdown (percentages of recognized songs)
    languages = profile.get("languages") or {}
    if languages:
        recog_total = profile.get("recognized_count") or sum(languages.values())
        sorted_langs = sorted(languages.items(), key=lambda x: x[1], reverse=True)
        msg += "🌍 <b>Language:</b>\n"
        for lang_code, count in sorted_langs:
            name, flag = language_label(lang_code)
            pct = (count / recog_total * 100) if recog_total else 0
            msg += f"  {flag} {name}: {count} ({pct:.0f}%)\n"

    # Unrecognized count
    unrecognized = total - (profile.get("recognized_count") or total)
    if unrecognized > 0:
        msg += f"  ⚠️ {unrecognized} unrecognized (not analyzed)\n"

    # Genre counter (percentages of recognized with genre)
    genres = profile.get("genres") or {}
    if genres:
        genre_total = sum(genres.values())
        sorted_genres = sorted(genres.items(), key=lambda x: x[1], reverse=True)
        msg += "🎸 <b>Genres:</b>\n"
        for g, c in sorted_genres[:5]:
            pct = (c / genre_total * 100) if genre_total else 0
            msg += f"  • {h(g)}: {pct:.0f}%\n"

    # Era stats
    years = profile.get("years") or []
    if years:
        msg += "📅 <b>Era:</b>\n"
        decades = {}
        for y in years:
            dec = (y // 10) * 10
            decades[dec] = decades.get(dec, 0) + 1
        top_decade, top_count = max(decades.items(), key=lambda x: x[1])
        msg += f"  Most songs from the <b>{top_decade}s</b>\n"
        if len(years) >= 5:
            msg += f"  Avg year: <b>{sum(years) // len(years)}</b>\n"

    msg += (
        "\n────────────────────────────\n"
        "💡 <b>Why this matters:</b> every song here makes your "
        "🎯 <b>For Me</b> recommendations more personal to you."
    )

    await update.message.reply_text(msg, parse_mode=PM, reply_markup=_main_menu_keyboard())


async def cmd_clearplaylist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear user's playlist (with confirmation)."""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    buttons = [
        [InlineKeyboardButton("🗑️ Yes, clear it", callback_data="confirm_clear")],
        [InlineKeyboardButton(label("cancel", lang), callback_data="cancel")],
    ]
    await update.message.reply_text(
        "🗑️ <b>Clear your playlist?</b>\n\nAll your songs and saved suggestions will be removed. This cannot be undone.",
        parse_mode=PM,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cmd_meforyou(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get songs matching user's taste based on similar tracks from playlist."""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    profile = await get_user_taste_profile(user_id)

    if profile["track_count"] == 0:
        await update.message.reply_text(
            M("for_me_empty", lang),
            parse_mode=PM,
            reply_markup=_main_menu_keyboard(lang),
        )
        return

    # For Me unlocks once the user has added 10+ songs (each adds ~5 similar
    # tracks to their pool, so there's a real pool to sample from).
    if profile["track_count"] < 10:
        remaining = 10 - profile["track_count"]
        await update.message.reply_text(
            M("for_me_locked", lang, count=profile["track_count"], remaining=remaining),
            parse_mode=PM,
            reply_markup=_main_menu_keyboard(lang),
        )
        return

    await update.message.chat.send_action("typing")

    try:
        # Sample random suggestions from the per-user pool (built at add time)
        pool_rows = await get_random_suggestions(user_id, count=5)

        if not pool_rows:
            await update.message.reply_text(
                M("for_me_no_pool", lang),
                parse_mode=PM,
                reply_markup=_main_menu_keyboard(lang),
            )
            return

        # Fetch live track details (IDs only in DB — keeps the pool tiny)
        recommended = []
        for track_id, source_id in pool_rows:
            try:
                track_data = await dz.get_track(track_id)
                if track_data:
                    recommended.append(track_data)
            except Exception as e:
                log.warning("[ME_FOR_YOU] fetch track %s failed: %s", track_id, e)

        if not recommended:
            await update.message.reply_text(
                M("for_me_fetch_fail", lang),
                parse_mode=PM,
                reply_markup=_main_menu_keyboard(lang),
            )
            return

        # Header with taste info
        msg = M("for_me_header", lang,
                count=profile["track_count"],
                bpm=f"{profile['avg_bpm']:.0f}",
                energy=f"{profile['avg_energy']:.2f}")
        msg += "\n\n"

        for i, track in enumerate(recommended, 1):
            msg += f"{i}. <b>{h(track.title)}</b> - {h(track.artist)}\n"
            msg += f"   <code>{h(track.title)} {h(track.artist)}</code>\n"
            if track.deezer_url:
                msg += f"   <a href=\"{track.deezer_url}\">▶️ Deezer</a>\n"
            msg += "\n"

        msg += M("for_me_footer", lang)

        await update.message.reply_text(msg, parse_mode=PM, disable_web_page_preview=True,
                                        reply_markup=_meforyou_keyboard(lang))

        # Send each preview as an audio message (30-sec Deezer preview)
        for track in recommended:
            if track.preview_url:
                try:
                    await asyncio.sleep(0.3)
                    await context.bot.send_audio(
                        chat_id=update.effective_chat.id,
                        audio=track.preview_url,
                        title=f"🎵 {track.title}",
                        performer=track.artist,
                        duration=30,
                    )
                except Exception as e:
                    log.warning("[ME_FOR_YOU] preview failed for %s: %s", track.title, e)

    except Exception as e:
        log.error("Recommendation error: %s", e, exc_info=True)
        await update.message.reply_text(
            "❌ Error finding recommendations. Try again.",
            reply_markup=_main_menu_keyboard(),
        )


async def cmd_playliststats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed playlist statistics."""
    profile = await get_user_taste_profile(update.effective_user.id)
    playlist = await get_user_playlist(update.effective_user.id)
    artists = await get_user_playlist_artists(update.effective_user.id, limit=10)

    if profile["track_count"] == 0:
        await update.message.reply_text(
            "❌ No playlist data yet!",
            reply_markup=_main_menu_keyboard(),
        )
        return

    msg = "📊 <b>Your Taste Profile</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    # Audio features
    msg += "🎵 <b>Audio Features:</b>\n"
    msg += f"🥁 Avg BPM: {profile['avg_bpm']:.0f}\n"
    msg += f"⚡ Avg Energy: {profile['avg_energy']:.2f}\n"
    msg += f"😊 Avg Valence: {profile['avg_valence']:.2f}\n"
    msg += f"📈 Total Songs: {profile['track_count']}\n\n"

    # Mood description
    if profile['avg_valence'] > 0.6 and profile['avg_energy'] > 0.5:
        mood = "🎉 Happy & Energetic"
    elif profile['avg_valence'] > 0.6 and profile['avg_energy'] < 0.3:
        mood = "😌 Calm & Happy"
    elif profile['avg_valence'] < 0.4 and profile['avg_energy'] > 0.5:
        mood = "😤 Intense & Dark"
    elif profile['avg_valence'] < 0.4 and profile['avg_energy'] < 0.3:
        mood = "😢 Sad & Melancholic"
    else:
        mood = "🎵 Balanced"

    msg += f"🎭 <b>Mood:</b> {mood}\n\n"

    # Top artists
    if artists:
        msg += "🎤 <b>Top Artists:</b>\n"
        for i, (artist, count) in enumerate(artists[:5], 1):
            msg += f"{i}. {h(artist)} ({count} songs)\n"

    await update.message.reply_text(msg, parse_mode=PM, reply_markup=_main_menu_keyboard())


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

async def post_init(application: Application):
    await init_db()
    await init_cache()
    # Register command shortcuts so they appear in Telegram's / menu (UX guide §10)
    try:
        await application.bot.set_my_commands([
            ("start", "Open main menu"),
            ("search", "Search a song"),
            ("meforyou", "Get songs for you"),
            ("myplaylist", "Your playlist"),
            ("language", "Change language / زبان"),
        ])
    except Exception as e:
        log.warning("set_my_commands failed: %s", e)
    log.info("Bot initialized: Last.fm=%s", "OK" if LASTFM_API_KEY else "off")


async def post_shutdown(application: Application):
    await dz.close()
    await mb.close()
    if lfm:
        await lfm.close()


def build_app() -> Application:
    builder = Application.builder().token(TELEGRAM_BOT_TOKEN).request(_http_request)
    builder.post_init(post_init)
    builder.post_shutdown(post_shutdown)
    app = builder.build()

    # Core commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("language", cmd_language))
    app.add_handler(CommandHandler("lang", cmd_language))

    # Phase 1: Quick Wins
    app.add_handler(CommandHandler("random", cmd_random))
    app.add_handler(CommandHandler("compare", cmd_compare))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("chart", cmd_chart))

    # Phase 2: Mood & Activity
    app.add_handler(CommandHandler("mood", cmd_mood))
    app.add_handler(CommandHandler("activity", cmd_activity))

    # Phase 3: Playlists
    app.add_handler(CommandHandler("playlist", cmd_playlist))
    app.add_handler(CommandHandler("playlists", cmd_playlists))

    # Phase 4: Taste
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("recommend", cmd_recommend))

    # Phase 5: Trivia
    app.add_handler(CommandHandler("trivia", cmd_trivia))

    # Phase 6: Lyrics
    app.add_handler(CommandHandler("lyrics", cmd_lyrics))
    app.add_handler(CommandHandler("searchlyrics", cmd_searchlyrics))

    # Phase 7: Share & Social
    app.add_handler(CommandHandler("share", cmd_share))
    app.add_handler(CommandHandler("top", cmd_top))

    # Phase 8: DNA
    app.add_handler(CommandHandler("dna", cmd_dna))

    # Phase 9: User Playlist
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("myplaylist", cmd_myplaylist))
    app.add_handler(CommandHandler("clearplaylist", cmd_clearplaylist))
    app.add_handler(CommandHandler("meforyou", cmd_meforyou))
    app.add_handler(CommandHandler("playliststats", cmd_playliststats))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(InlineQueryHandler(inline_query_handler))

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        log.warning("Unhandled error: %s", context.error)
    app.add_error_handler(error_handler)
    return app


def main():
    threading.Thread(target=run_http_server, daemon=True).start()
    app = build_app()
    log.info("Music Suggest Bot v3 starting...")
    print("\n" + "=" * 50)
    print("  MUSIC SUGGEST BOT v3")
    print("  Full Featured Music Discovery Platform")
    print("=" * 50 + "\n")
    print("  Commands:")
    print("  /start, /help, /random, /compare")
    print("  /mood, /activity, /playlist, /trivia")
    print("  /profile, /recommend, /lyrics, /dna")
    print("  /share, /top, /chart, /history")
    print("=" * 50 + "\n")
    app.run_polling()


if __name__ == "__main__":
    main()
