#!/usr/bin/env python3
"""
Music Discovery Telegram Bot (Deezer-only)
───────────────────────────────────────────
Completely free. No API keys needed for the main flow.
Optionally add LASTFM_API_KEY for richer similar tracks.

Deployable on free cloud hosts (Render, Railway, Koyeb, Fly.io).
"""

import logging
import os
import asyncio
from typing import Optional

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, filters, MessageHandler

# Load .env only if it exists (for local dev — cloud uses env vars directly)
if os.path.exists(".env"):
    load_dotenv()

from deezer_helper import DeezerClient, TrackInfo

# ═══════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PORT = int(os.environ.get("PORT", 8080))
HOST = os.environ.get("HOST", "0.0.0.0")
AUDD_TOKEN = os.environ.get("AUDD_API_TOKEN", "")
LASTFM_KEY = os.environ.get("LASTFM_API_KEY", "")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

dz = DeezerClient()
_user_state: dict[int, dict] = {}


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
    """Text message → Deezer search → 'Did you mean?'."""
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
        f"🔍 *Results for:* _{query}_\n\n"
        f"Which one did you mean?",
        reply_markup=_did_you_mean_keyboard(results),
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_audio(update: Update, context):
    """Audio upload → AudD recognition (optional, needs token)."""
    if not AUDD_TOKEN:
        await update.message.reply_text(
            "🎤 I got your audio file, but recognition isn't configured.\n"
            "Type the song name instead please."
        )
        return

    await update.message.chat.send_action("typing")

    import io
    import aiohttp

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
    """Inline button responses."""
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
        await query.edit_message_text(
            "Which one did you mean?",
            reply_markup=_did_you_mean_keyboard(results),
        )
        return

    if data.startswith("pick_"):
        idx = int(data.split("_")[1])
        results: list[TrackInfo] = state.get("results", [])
        if idx < 0 or idx >= len(results):
            await query.edit_message_text("Selection expired. Search again.")
            _user_state.pop(chat_id, None)
            return

        selected_raw = results[idx]
        await query.edit_message_text(
            f"⏳ Analysing *{selected_raw.title}*…",
            parse_mode=ParseMode.MARKDOWN,
        )

        # Get full track details (inc. BPM, genres)
        selected = dz.get_track(selected_raw.id)
        if not selected:
            selected = selected_raw

        # Get similar tracks via Deezer radio
        similar = dz.get_similar(selected.id, limit=10)

        # If Last.fm is configured, also grab similar from there
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

        # Build the response
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
                lines.append(
                    f"🎧 *{s.title}* — {s.artist}  ·  {s.bpm_str()}"
                )
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

        await query.message.reply_text(
            msg,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False,
        )

        _user_state.pop(chat_id, None)


# ═══════════════════════════════════════════════════
# Web health endpoint (keeps free hosts alive)
# ═══════════════════════════════════════════════════

async def health_check(request):
    return "OK — Music Bot running"


async def run_web_server():
    """Minimal HTTP server so free cloud hosts don't kill the bot."""
    from aiohttp import web
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    log.info(f"Web server running on {HOST}:{PORT}")


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

async def main():
    # Start web server
    await run_web_server()

    # Start Telegram bot
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    app.add_handler(CallbackQueryHandler(handle_callback))

    log.info("🎵 Music Suggest Bot starting...")
    log.info(f"   Deezer: OK (no key needed)")
    log.info(f"   AudD: {'OK' if AUDD_TOKEN else 'not configured'}")
    log.info(f"   Last.fm: {'OK' if LASTFM_KEY else 'not configured'}")

    # Use webhook if deployed, polling otherwise
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"
        log.info(f"Setting webhook: {webhook_url}")
        await app.bot.set_webhook(url=webhook_url)
        # Run with webhook — using aiohttp
        from telegram.ext import Updater
        # python-telegram-bot v20+ uses Application.run_webhook
        await app.run_webhook(
            listen=HOST,
            port=PORT,
            url_path="webhook",
            webhook_url=webhook_url,
        )
    else:
        log.info("Running in polling mode (no RENDER_EXTERNAL_URL set)")
        await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
