"""
PythonAnywhere WSGI entry point for Music Suggest Bot.

Setup:
  1. In PythonAnywhere Web tab, set WSGI file to this path
  2. Set env vars in PA: TELEGRAM_BOT_TOKEN, AUDD_API_TOKEN, LASTFM_API_KEY
  3. Visit https://susispolo.pythonanywhere.com/setup once
  4. Your bot is live!
"""
import os, sys, json, asyncio, logging

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_DIR, ".env"))

from bot import build_app
from telegram import Update
from logging_config import setup_logging

setup_logging(level=logging.INFO, log_file=os.path.join(PROJECT_DIR, "bot.log"))
log = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_URL = "https://susispolo.pythonanywhere.com/webhook"

app = build_app()
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    method = environ.get("REQUEST_METHOD", "GET")

    if path == "/webhook" and method == "POST":
        content_length = int(environ.get("CONTENT_LENGTH", 0))
        body = environ["wsgi.input"].read(content_length)
        try:
            update = Update.de_json(json.loads(body.decode()), app.bot)
            loop.run_until_complete(app.process_update(update))
        except Exception as e:
            log.error("Webhook error: %s", e)
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"OK"]

    if path in ("/", "/health"):
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"OK"]

    if path == "/setup" and method == "GET":
        import requests
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/setWebhook",
                          data={"url": WEBHOOK_URL}, timeout=15)
        start_response("200 OK", [("Content-Type", "application/json")])
        return [json.dumps(r.json(), indent=2).encode()]

    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"Not Found"]
