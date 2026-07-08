#!/usr/bin/env python3
"""
Music Discovery Telegram Bot (Deezer-only)
───────────────────────────────────────────
Completely free. No API keys needed for the main flow.
Designed for Replit + UptimeRobot (free, no credit card).
"""

import logging
import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import aiohttp
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, filters, MessageHandler

if os.path.exists(".env"):
    load_dotenv()

from deezer_helper import DeezerClient, TrackInfo

# ═══════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
PORT = int(os.environ.get("PORT", 8080))
AUDD_TOKEN = os.environ.get("AUDD_API_TOKEN", "")
LASTFM_KEY = os.environ.get("LASTFM_API_KEY", "")

# Proxy for Telegram (Iran / filtered regions)
# Set TELEGRAM_PROXY env var like:
#   socks5://127.0.0.1:1080
#   http://127.0.0.1:8080
PROXY_URL = os.environ.get("TELEGRAM_PROXY", "")

# Custom request with higher timeouts
from telegram.request import HTTPXRequest
_http_request = HTTPXRequest(
    connect_timeout=30.0,
    read_timeout=15.0,
    write_timeout=15.0,
    pool_timeout=5.0,
)

dz = DeezerClient()
_user_state: dict[int, dict] = {}


# ═══════════════════════════════════════════════════
# Web server (just for UptimeRobot pings)
# ═══════════════════════════════════════════════════

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass  # suppress logs

def run_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    log.info(f"Health server on port {PORT}")
    server.serve_forever()


# ═══════════════════════════════════════════════════
# Inline keyboard builders
# ═══════════════════════════════════════════════════

def _did_you_mean_keyboard(results: list[TrackInfo]) -> InlineKeyboardMarkup:
    buttons = []
    for i, t in enumerate(results):
        label = f"{t.title} — {t.artist}"
        if len(label) > 60:
            label = label[:57] + "..."
        buttons.append([InlineKeyboardButton(label, callback_data=f"pick_{i}")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


# ═══════════════════════════════════════════════════
# Telegram Handlers
# ═══════════════════════════════════════════════════

async def start(update: Update, context):
    await update.message.reply_text(
        "🎵 *Music Suggest Bot*\n\n"
        "Send me a song name and I'll find similar music!\n\n"
        "Examples:\n"
        "  `Bohemian Rhapsody`\n"
        "  `Blinding Lights The Weeknd`\n"
        "  `Hotel California`\n\n"
        "Or upload an MP3 and I'll recognise it (if configured).\n\n"
        "_Powered by Deezer + Last.fm — 100% free_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_text(update: Update, context):
    query = update.message.text.strip()
    if not query:
        return

    await update.message.chat.send_action("typing")

    try:
        results = dz.search(query, limit=5)
    except Exception as e:
        log.warning("Deezer search failed: %s", e)
        await update.message.reply_text("⚠️ Search failed — Deezer API timed out. Your VPN connection might be unstable, or Deezer is slow right now. Try again in a moment.")
        return

    if not results:
        await update.message.reply_text("😕 No results found. Try another search.")
        return

    _user_state[update.effective_chat.id] = {"results": results, "query": query}

    await update.message.reply_text(
        f"🔍 *Results for:* _{query}_\n\nWhich one did you mean?",
        reply_markup=_did_you_mean_keyboard(results),
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_audio(update: Update, context):
    """Handle audio/voice messages — extract filename or metadata and search."""
    await update.message.chat.send_action("typing")

    # Extract metadata from Telegram Audio object
    audio = update.message.effective_attachment
    query = ""
    source = ""

    if hasattr(audio, "file_name") and audio.file_name:
        # Try parsing filename like "Artist - Song.mp3" or "Song - Artist.mp3"
        raw = audio.file_name.rsplit(".", 1)[0]  # strip extension
        # Common patterns: "Artist - Song", "Song - Artist", "Artist_Song"
        if " - " in raw:
            parts = raw.split(" - ", 1)
            query = f"{parts[0]} {parts[1]}"
            source = "filename"
        elif "_" in raw:
            query = raw.replace("_", " ")
            source = "filename"
        else:
            query = raw
            source = "filename"

    # Use Telegram's own audio metadata if available (more reliable)
    if hasattr(audio, "performer") and audio.performer:
        title_part = getattr(audio, "title", "") or ""
        if title_part:
            query = f"{title_part} {audio.performer}"
            source = "metadata"
        else:
            query = audio.performer if not query else query
            source = "metadata" if source != "filename" else source

    # If we got a decent query from metadata, search immediately
    if query and len(query) >= 3:
        await update.message.reply_text(
            f"🔍 Searching: *{query}*…", parse_mode=ParseMode.MARKDOWN
        )
        try:
            results = dz.search(query, limit=5)
        except Exception as e:
            log.warning("Deezer search from audio failed: %s", e)
            results = []

        if results:
            _user_state[update.effective_chat.id] = {"results": results, "query": query}
            await update.message.reply_text(
                f"🔍 *Results from {source}:*",
                reply_markup=_did_you_mean_keyboard(results),
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    # Fallback: try AudD if token is valid
    if AUDD_TOKEN:
        await update.message.reply_text("🎤 Trying to recognise audio…")
        import io
        try:
            file = await audio.get_file()
            file_bytes = await file.download_as_bytearray()
        except Exception as e:
            log.warning("File download failed: %s", e)
            await update.message.reply_text("Couldn't download. Type the song name instead.")
            return
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field("api_token", AUDD_TOKEN)
                data.add_field("return", "deezer")
                data.add_field("file", io.BytesIO(file_bytes), filename="audio.mp3",
                               content_type="audio/mpeg")
                async with session.post(
                    "https://api.audd.io/", data=data,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    result = await resp.json()
        except Exception as e:
            log.warning("AudD failed: %s", e)
            await update.message.reply_text("Type the song name instead.")
            return
        error_code = result.get("error", {}).get("error_code")
        if error_code == 900:
            await update.message.reply_text(
                "🎤 AudD token is invalid. Type the song name instead."
            )
            return
        if result.get("status") == "success" and result.get("result"):
            track_data = result["result"]
            title = track_data.get("title", "")
            artist = track_data.get("artist", "")
            _user_state[update.effective_chat.id] = {"recognised_name": f"{title} {artist}"}
            await update.message.reply_text(
                f"🎤 I heard: *{title}* — *{artist}*\nIs that right?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Yes, find similar", callback_data="confirm_recog")],
                    [InlineKeyboardButton("❌ No, type instead", callback_data="cancel")],
                ]),
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    # Nothing worked
    await update.message.reply_text(
        "🎤 Couldn't identify the song from the file name or audio.\n"
        "Type the song name instead please."
    )


async def handle_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    data = query.data
    state = _user_state.get(chat_id, {})

    if data == "cancel":
        await query.edit_message_text("Alright, cancelled.")
        _user_state.pop(chat_id, None)
        return

    if data == "confirm_recog":
        name = state.get("recognised_name", "")
        if not name:
            await query.edit_message_text("Something went wrong. Try again.")
            return
        await query.edit_message_text(f"🔍 Searching for *{name}*…",
                                       parse_mode=ParseMode.MARKDOWN)
        try:
            results = dz.search(name, limit=5)
        except Exception as e:
            log.warning("search in confirm_recog failed: %s", e)
            await query.edit_message_text("⚠️ Search failed. Deezer API timed out. Try again.")
            return
        if not results:
            await query.edit_message_text("😕 No results found.")
            return
        _user_state[chat_id] = {"results": results}
        await query.edit_message_text("Which one did you mean?",
                                       reply_markup=_did_you_mean_keyboard(results))
        return

    if data.startswith("pick_"):
        idx = int(data.split("_")[1])
        results: list[TrackInfo] = state.get("results", [])
        if idx < 0 or idx >= len(results):
            await query.edit_message_text("Selection expired. Search again.")
            _user_state.pop(chat_id, None)
            return

        selected_raw = results[idx]
        await query.edit_message_text(f"⏳ Analysing *{selected_raw.title}*…",
                                       parse_mode=ParseMode.MARKDOWN)

        try:
            selected = dz.get_track(selected_raw.id)
        except Exception as e:
            log.warning("get_track failed: %s", e)
            selected = None
        if not selected:
            selected = selected_raw

        similar = []
        similar_label = ""
        lastfm_similar = []
        try:
            similar = dz.get_similar(selected.id, limit=10)
            if not similar:
                # Fallback: artist top tracks
                similar = dz.get_artist_top(selected.artist_id, limit=10)
                if similar:
                    similar_label = "from same artist"  # flagged below
        except Exception as e:
            log.warning("similar fetch failed: %s", e)

        if not similar:
            # Last resort: search by artist name
            try:
                similar = dz.search(selected.artist, limit=5)
                similar = [s for s in similar if s.id != selected.id][:10]
                if similar:
                    similar_label = "other tracks from this artist"
            except Exception as e:
                log.warning("fallback search failed: %s", e)

        if LASTFM_KEY:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://ws.audioscrobbler.com/2.0/",
                        params={
                            "method": "track.getsimilar",
                            "track": selected.title,
                            "artist": selected.artist,
                            "api_key": LASTFM_KEY,
                            "format": "json",
                            "limit": 10,
                            "autocorrect": 1,
                        },
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as resp:
                        if resp.status == 200:
                            lr = await resp.json()
                            lastfm_similar = lr.get("similartracks", {}).get("track", [])
            except Exception as e:
                log.warning("Last.fm failed: %s", e)

        lines = [
            f"*━━━ Selected Track ━━━*",
            "",
            f"🎵 *{selected.title}*",
            f"👤 {selected.artist}",
            f"💿 {selected.album}",
            f"🎶 Tempo: {selected.bpm_str()}",
            f"⏱️ {selected.duration_str()}",
        ]
        if selected.genres:
            lines.append(f"🏷️ {', '.join(selected.genres[:4])}")
        if selected.explicit:
            lines.append("🔞 Explicit")
        lines.append("")
        lines.append(f"[▶️ Listen on Deezer]({selected.deezer_url})")
        if selected.preview_url:
            lines.append(f"[🎧 30s Preview]({selected.preview_url})")
        lines.append("")

        if similar:
            header = f"*━━━ 📻 Similar ({similar_label}) ━━━*" if similar_label else f"*━━━ 📻 {len(similar)} Similar ━━━*"
            lines.append(header)
            lines.append("")
            for s in similar:
                lines.append(f"🎧 *{s.title}* — {s.artist}  ·  {s.bpm_str()}")
                lines.append(f"   [▶️ Deezer]({s.deezer_url})")
                lines.append("")

        if lastfm_similar:
            lines.append(f"*━━━ 👥 Similar on Last.fm ━━━*")
            lines.append("")
            for ls in lastfm_similar[:5]:
                name = ls.get("name", "")
                l_artist = ls.get("artist", {}).get("name", "")
                l_url = ls.get("url", "")
                match = ls.get("match", 0)
                try:
                    pct = f" ({float(match)*100:.0f}% match)"
                except (ValueError, TypeError):
                    pct = ""
                lines.append(f"👤 *{name}* — {l_artist}{pct}")
                if l_url:
                    lines.append(f"   [Listen]({l_url})")
                lines.append("")

        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:3997] + "…"

        await query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN,
                                        disable_web_page_preview=False)
        _user_state.pop(chat_id, None)


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

def build_app() -> Application:
    """Build the Application (shared by polling and webhook modes)."""
    builder = Application.builder().token(TOKEN).request(_http_request)
    if PROXY_URL:
        builder = builder.proxy(PROXY_URL)
    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    app.add_handler(CallbackQueryHandler(handle_callback))

    async def error_handler(update: object, context):
        log.warning("Unhandled error (logged): %s", context.error)
    app.add_error_handler(error_handler)
    return app


def main():
    # Start health server in background (for UptimeRobot)
    t = threading.Thread(target=run_http_server, daemon=True)
    t.start()

    app = build_app()
    log.info("🎵 Music Suggest Bot starting...")
    log.info(f"   Deezer: OK (no key needed)")
    log.info(f"   AudD: {'OK' if AUDD_TOKEN else 'not configured'}")
    log.info(f"   Last.fm: {'OK' if LASTFM_KEY else 'not configured'}")

    print("\n" + "="*50)
    print("  ✅ BOT IS RUNNING!")
    print("  📱 Go talk to your bot on Telegram")
    print("  🔗 https://uptimerobot.com → ping this URL")
    print("="*50 + "\n")

    app.run_polling()


if __name__ == "__main__":
    main()
