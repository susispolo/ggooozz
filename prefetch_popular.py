#!/usr/bin/env python3
"""
Pre-fetch audio features for popular songs.
Runs periodically via cron or scheduler to cache song data
so user requests are instant.
"""

import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

from config import LASTFM_API_KEY
from deezer_helper import DeezerClient, TrackInfo
from musicbrainz_client import MusicBrainzClient
from lastfm_client import LastfmClient
from audio_analyzer import analyze_audio
from feature_cache import (
    init_cache, get_cached_features, cache_features,
    was_recently_prefetched, get_cache_stats, cleanup_old_entries
)
from language_detect import detect_language

# Log to prefetch.log file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    handlers=[
        logging.FileHandler('prefetch.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

# Configuration
TARGET_SONGS_PER_RUN = 15  # Safe rate limits
MIN_CACHE_HOURS = 24  # Don't re-fetch songs cached less than 24 hours ago

# Persian genre IDs on Deezer (for targeted prefetching)
PERSIAN_GENRE_ID = 196  # Iranian/Persian music genre ID on Deezer


class PrefetchStats:
    """Track prefetch statistics."""

    def __init__(self):
        self.fetched = 0
        self.skipped = 0
        self.errors = 0
        self.start_time = time.time()

    def summary(self) -> str:
        elapsed = time.time() - self.start_time
        return (
            f"Fetched: {self.fetched} | "
            f"Skipped: {self.skipped} | "
            f"Errors: {self.errors} | "
            f"Time: {elapsed:.1f}s"
        )


async def should_prefetch(track_id: int) -> bool:
    """Check if a track needs prefetching."""
    # Skip if recently prefetched (within MIN_CACHE_HOURS)
    if await was_recently_prefetched(track_id, hours=MIN_CACHE_HOURS):
        return False

    # Skip if already fully cached
    cached = await get_cached_features(track_id)
    if cached and (cached.get("audio_features") or cached.get("acoustic_features")):
        return False

    return True


async def prefetch_song(
    track: TrackInfo,
    dz: DeezerClient,
    mb: MusicBrainzClient,
    lfm: Optional[LastfmClient],
    stats: PrefetchStats
) -> bool:
    """
    Pre-fetch all features for a single song.
    Returns True if new features were cached.
    """
    track_id = track.id

    # Check if we should prefetch
    if not await should_prefetch(track_id):
        stats.skipped += 1
        log.debug("[PREFETCH] Skip (cached): %s - %s", track.artist, track.title)
        return False

    log.info("[PREFETCH] Fetching: %s - %s (ID: %d)", track.artist, track.title, track_id)

    try:
        # Run analysis tasks in parallel
        audio_features = None
        acoustic_features = None
        musicbrainz_id = None
        lastfm_tags = []

        # Task 1: Audio analysis (if preview available)
        audio_task = None
        if track.preview_url:
            audio_task = analyze_audio(track.preview_url)

        # Task 2: MusicBrainz search
        mb_task = mb.search_recording(track.artist, track.title)

        # Task 3: Last.fm tags
        lastfm_task = None
        if lfm:
            lastfm_task = lfm.get_track_tags(track.artist, track.title)

        # Execute parallel tasks
        results = await asyncio.gather(
            audio_task or asyncio.sleep(0),
            mb_task,
            lastfm_task or asyncio.sleep(0),
            return_exceptions=True
        )

        # Parse results
        audio_result, mb_result, lastfm_result = results

        # Handle audio features
        if not isinstance(audio_result, Exception) and audio_result:
            audio_features = audio_result

        # Handle MusicBrainz
        if not isinstance(mb_result, Exception) and mb_result:
            musicbrainz_id = mb_result.get("musicbrainz_id")
            acoustic_features = mb_result.get("acoustic_features")

        # Handle Last.fm
        if not isinstance(lastfm_result, Exception) and lastfm_result:
            lastfm_tags = lastfm_result.get("tags", [])

        # Cache the results
        await cache_features(
            track_id, track.title, track.artist,
            audio_features, acoustic_features,
            musicbrainz_id, lastfm_tags
        )

        stats.fetched += 1
        log.info("[PREFETCH] ✓ Cached: %s - %s", track.artist, track.title)
        return True

    except Exception as e:
        stats.errors += 1
        log.error("[PREFETCH] ✗ Error for %s - %s: %s", track.artist, track.title, e)
        return False


async def get_popular_songs(dz: DeezerClient, limit: int = 30) -> list[TrackInfo]:
    """Fetch trending songs from multiple sources."""
    all_tracks = []

    # Source 1: Global charts
    try:
        global_chart = await dz.get_chart(chart_id=0, limit=limit // 2)
        all_tracks.extend(global_chart)
        log.info("[PREFETCH] Fetched %d tracks from global chart", len(global_chart))
    except Exception as e:
        log.warning("[PREFETCH] Failed to fetch global chart: %s", e)

    # Source 2: Most streamed this week
    try:
        weekly_chart = await dz.get_chart(chart_id=1, limit=limit // 4)
        all_tracks.extend(weekly_chart)
        log.info("[PREFETCH] Fetched %d tracks from weekly chart", len(weekly_chart))
    except Exception as e:
        log.warning("[PREFETCH] Failed to fetch weekly chart: %s", e)

    # Source 3: Persian music (if configured)
    try:
        persian_chart = await dz.get_genre_charts(genre_id=PERSIAN_GENRE_ID, limit=limit // 4)
        all_tracks.extend(persian_chart)
        log.info("[PREFETCH] Fetched %d tracks from Persian chart", len(persian_chart))
    except Exception as e:
        log.warning("[PREFETCH] Failed to fetch Persian chart: %s", e)

    # Deduplicate by track ID
    seen_ids = set()
    unique_tracks = []
    for track in all_tracks:
        if track.id not in seen_ids:
            seen_ids.add(track.id)
            unique_tracks.append(track)

    log.info("[PREFETCH] Total unique tracks: %d", len(unique_tracks))
    return unique_tracks


async def run_prefetch(target_songs: Optional[int] = None):
    """Main prefetch execution."""
    target = target_songs or TARGET_SONGS_PER_RUN
    stats = PrefetchStats()

    log.info("=" * 60)
    log.info("[PREFETCH] Starting prefetch run (target: %d songs)", target)
    log.info("=" * 60)

    # Initialize clients
    dz = DeezerClient()
    mb = MusicBrainzClient()
    lfm = LastfmClient(LASTFM_API_KEY) if LASTFM_API_KEY else None

    try:
        # Initialize cache database
        await init_cache()

        # Get popular songs
        popular = await get_popular_songs(dz, limit=target * 2)

        # Prefetch songs until we reach target
        for track in popular:
            if stats.fetched >= target:
                break
            await prefetch_song(track, dz, mb, lfm, stats)

        # Print summary
        log.info("=" * 60)
        log.info("[PREFETCH] Run complete: %s", stats.summary())
        log.info("=" * 60)

        # Print cache stats
        cache_stats = await get_cache_stats()
        log.info("[CACHE] Total cached: %d songs", cache_stats.get("total_songs", 0))

    finally:
        # Cleanup
        await dz.close()
        await mb.close()
        if lfm:
            await lfm.close()

    return stats


async def run_cleanup(days_old: int = 30):
    """Remove old cached songs not accessed in N days."""
    log.info("[CLEANUP] Removing entries older than %d days...", days_old)
    removed = await cleanup_old_entries(days_old)
    log.info("[CLEANUP] Removed %d old entries", removed)
    return removed


def main():
    """Entry point for command line."""
    import argparse

    parser = argparse.ArgumentParser(description="Pre-fetch popular songs")
    parser.add_argument(
        "--target", "-t",
        type=int,
        default=TARGET_SONGS_PER_RUN,
        help=f"Target number of songs to fetch (default: {TARGET_SONGS_PER_RUN})"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Run cleanup instead of prefetch"
    )
    parser.add_argument(
        "--cleanup-days",
        type=int,
        default=30,
        help="Days old for cleanup (default: 30)"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show cache statistics"
    )

    args = parser.parse_args()

    if args.stats:
        async def show_stats():
            await init_cache()
            stats = await get_cache_stats()
            print("\n=== Cache Statistics ===")
            print(f"Total songs: {stats.get('total_songs', 0)}")
            print(f"With audio features: {stats.get('with_audio', 0)}")
            print(f"With acoustic features: {stats.get('with_acoustic', 0)}")
            print(f"With MusicBrainz ID: {stats.get('with_mbid', 0)}")
            print(f"With Last.fm tags: {stats.get('with_tags', 0)}")
            print(f"Last 24h: {stats.get('recent_24h', 0)}")
            print(f"Last 7 days: {stats.get('recent_7d', 0)}")
            print("========================\n")

        asyncio.run(show_stats())

    elif args.cleanup:
        asyncio.run(run_cleanup(args.cleanup_days))

    else:
        asyncio.run(run_prefetch(args.target))


if __name__ == "__main__":
    main()
