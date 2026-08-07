"""
Centralized configuration for Music Suggest Bot v2.
"""
import os
import sys
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


def validate_config():
    """Validate required configuration on startup."""
    errors = []

    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN is required")

    if errors:
        print("\n" + "="*60)
        print("❌ CONFIGURATION ERROR")
        print("="*60)
        for error in errors:
            print(f"  • {error}")
        print("\nPlease set the required environment variables.")
        print("You can use a .env file or export them directly.")
        print("="*60 + "\n")
        sys.exit(1)

    # Warn about optional but recommended keys
    warnings = []
    if LASTFM_API_KEY == "8bbf8ef16db2639e7515e00a9330348a":
        warnings.append("Using default Last.fm API key (limited features)")
    if not AUDD_API_TOKEN:
        warnings.append("AUDD_API_TOKEN not set (audio recognition disabled)")

    if warnings:
        print("\n⚠️  WARNINGS:")
        for warning in warnings:
            print(f"  • {warning}")
        print()
