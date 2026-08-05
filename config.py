"""
Centralized configuration for Music Suggest Bot v2.
"""
import os
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_PROXY = os.environ.get("TELEGRAM_PROXY", "")

# APIs
LASTFM_API_KEY = os.environ.get("LASTFM_API_KEY", "8bbf8ef16db2639e7515e00a9330348a")
AUDD_API_TOKEN = os.environ.get("AUDD_API_TOKEN", "")

# Server
PORT = int(os.environ.get("PORT", 8080))

# Feature Cache
CACHE_DB_PATH = "feature_cache.db"
USER_PREFS_DB_PATH = "user_prefs.db"

# Timeouts (seconds)
DEEZER_TIMEOUT = 10
MUSICBRAINZ_TIMEOUT = 10
ACOUSTICBRAINZ_TIMEOUT = 15
LASTFM_TIMEOUT = 8
AUDIO_DOWNLOAD_TIMEOUT = 30

# Rate Limits (requests per second)
MUSICBRAINZ_RATE_LIMIT = 1  # 1 req/sec
LASTFM_RATE_LIMIT = 5  # 5 req/sec

# Analysis
MAX_CONCURRENT_ANALYSES = 5  # Limit simultaneous librosa runs
PREVIEW_DURATION = 30  # Deezer preview length in seconds
