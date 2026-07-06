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
        await update.message.reply_text("Search failed. Try again later.")
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
    if not AUDD_TOKEN:
        await update.message.reply_text(
            "🎤 I got your audio, but recognition isn't configured.\nType the song name instead please."
        )
        return

    await update.message.chat.send_action("typing")
    import io, aiohttp

    try:
        file = await update.message.effective_attachment.get_file()
        file_bytes = await file.download_as_bytearray()
    except Exception as e:
        log.warning("File download failed: %s", e)
        await update.message.reply_text("Couldn't download your audio. Try typing the name.")
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
        await update.message.reply_text("Couldn't recognise it. Try typing the name.")
        return

    status = result.get("status")
    if status != "success" or not result.get("result"):
        await update.message.reply_text("Couldn't recognise the song. Please type the name.")
        return

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
        results = dz.search(name, limit=5)
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

        selected = dz.get_track(selected_raw.id)
        if not selected:
            selected = selected_raw

        similar = dz.get_similar(selected.id, limit=10)

        lastfm_similar: list[dict] = []
        if LASTFM_KEY:
            try:
                import requests
                lr = requests.get(
                    "https://ws.audioscrobbler.com/2.0/",
                    params={
                        "method": "track.getsimilar",
                        "track": selected.title,
                        "artist": selected.artist,
                        "api_key": LASTFM_KEY,
                        "format": "json",
                        "limit": 5,
                    },
                    timeout=10,
                )
                if lr.status_code == 200:
                    lastfm_similar = lr.json().get("similartracks", {}).get("track", [])
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
            lines.append(f"*━━━ 📻 {len(similar)} Similar on Deezer ━━━*")
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

def main():
    # Start health server in background (for UptimeRobot)
    t = threading.Thread(target=run_http_server, daemon=True)
    t.start()

    # Start Telegram bot (polling) — with optional proxy for filtered regions
    if PROXY_URL:
        log.info(f"   Proxy: {PROXY_URL}")
        app = Application.builder().token(TOKEN).proxy(PROXY_URL).build()
    else:
        app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    app.add_handler(CallbackQueryHandler(handle_callback))

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
