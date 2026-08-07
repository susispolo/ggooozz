#!/usr/bin/env python3
"""
Comprehensive artist-based prefetch system.
Fetches top artists by genre, gets all their songs, and pre-analyzes everything.
Includes similar songs discovery and hourly reporting.
"""

import asyncio
import logging
import sys
import time
import json
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
from collections import defaultdict

from config import LASTFM_API_KEY, TELEGRAM_BOT_TOKEN
from deezer_helper import DeezerClient, TrackInfo
from musicbrainz_client import MusicBrainzClient
from lastfm_client import LastfmClient
from audio_analyzer import analyze_audio
from feature_cache import (
    init_cache, get_cached_features, cache_features,
    was_recently_prefetched, get_cache_stats, cleanup_old_entries,
    get_connection
)
from language_detect import detect_language
from similarity_engine import rank_by_similarity, SimilarityResult

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    handlers=[
        logging.FileHandler('prefetch_artists.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════

# Genre targets - Deezer genre IDs
# Note: These are Deezer's internal genre IDs, not universal
# Valid IDs: 132 (Pop), 116 (Rap/Hip Hop), 152 (Rock), etc.
# Persian music is NOT a separate genre on Deezer
GENRE_TARGETS = {
    "pop": {"artist_count": 200, "genre_ids": [132], "name": "Pop"},
    "rap": {"artist_count": 100, "genre_ids": [116], "name": "Rap/Hip-Hop"},
    "rock": {"artist_count": 100, "genre_ids": [152], "name": "Rock"},
    "rnb": {"artist_count": 100, "genre_ids": [165], "name": "R&B"},
}

# Persian artists will be fetched from your persian_genres.json database
PERSIAN_ARTISTS_COUNT = 100

# Similar songs per track
SIMILAR_SONGS_PER_TRACK = 5

# Rate limiting
MAX_SONGS_PER_HOUR = 500  # ~8 songs/minute
MAX_API_CALLS_PER_MINUTE = 50  # Stay safe with APIs

# Hourly report time
REPORT_HOUR_INTERVAL = 1  # Send report every hour


# ═══════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════

@dataclass
class PrefetchProgress:
    """Track prefetch progress for reporting."""
    genre: str
    artists_total: int = 0
    artists_completed: int = 0
    songs_total: int = 0
    songs_completed: int = 0
    similar_songs_found: int = 0
    errors: int = 0
    start_time: float = 0.0
    last_report_time: float = 0.0

    def artists_remaining(self) -> int:
        return self.artists_total - self.artists_completed

    def songs_remaining(self) -> int:
        return self.songs_total - self.songs_completed

    def elapsed_hours(self) -> float:
        return (time.time() - self.start_time) / 3600

    def songs_per_hour(self) -> float:
        hours = self.elapsed_hours()
        return self.songs_completed / hours if hours > 0 else 0

    def estimated_hours_remaining(self) -> float:
        rate = self.songs_per_hour()
        if rate <= 0:
            return float('inf')
        return self.songs_remaining() / rate


@dataclass
class HourlyReport:
    """Hourly progress report."""
    timestamp: str
    artists_added: list[str]
    songs_added: int
    similar_songs_added: int
    total_cached: int
    errors: int
    genre_breakdown: dict


# ═══════════════════════════════════════════════════
# Artist Fetching
# ═══════════════════════════════════════════════════

async def list_deezer_genres(dz: DeezerClient) -> list[dict]:
    """List all available genres on Deezer (for debugging)."""
    data = await dz._request_with_retry(f"{dz.BASE}/genre")
    genres = data.get("data", [])
    return [{"id": g["id"], "name": g["name"]} for g in genres]


async def get_persian_artists(limit: int = 100) -> list[dict]:
    """Get Persian artists from persian_genres.json database."""
    import json
    import os

    artists = []

    # Load from persian_genres.json
    if os.path.exists("persian_genres.json"):
        try:
            with open("persian_genres.json", "r", encoding="utf-8") as f:
                persian_db = json.load(f)

            for artist_name, genres in persian_db.items():
                artists.append({
                    "name": artist_name,
                    "genres": genres,
                    "source": "persian_genres.json"
                })

            log.info("[PERSIAN] Loaded %d artists from persian_genres.json", len(artists))
        except Exception as e:
            log.error("[PERSIAN] Failed to load persian_genres.json: %s", e)

    # Also load from new_persian_artists.json
    if os.path.exists("new_persian_artists.json"):
        try:
            with open("new_persian_artists.json", "r", encoding="utf-8") as f:
                new_artists = json.load(f)

            for artist_name, genres in new_artists.items():
                # Skip if already in main database
                if not any(a["name"] == artist_name for a in artists):
                    artists.append({
                        "name": artist_name,
                        "genres": genres,
                        "source": "new_persian_artists.json"
                    })

            log.info("[PERSIAN] Loaded %d additional artists from new_persian_artists.json",
                    len(new_artists))
        except Exception as e:
            log.error("[PERSIAN] Failed to load new_persian_artists.json: %s", e)

    # Sort alphabetically and return top N
    artists.sort(key=lambda x: x["name"])
    return artists[:limit]


async def search_artist_on_deezer(dz: DeezerClient, artist_name: str) -> Optional[dict]:
    """Search for an artist on Deezer and return their info."""
    try:
        data = await dz._request_with_retry(
            f"{dz.BASE}/search/artist",
            params={"q": artist_name, "limit": 1}
        )

        artists = data.get("data", [])
        if artists:
            artist = artists[0]
            return {
                "id": artist.get("id"),
                "name": artist.get("name"),
                "nb_album": artist.get("nb_album", 0),
                "nb_fan": artist.get("nb_fan", 0)
            }
    except Exception as e:
        log.warning("[SEARCH] Failed to search for artist %s: %s", artist_name, e)

    return None


async def get_top_artists_by_genre(
    dz: DeezerClient,
    genre_ids: list[int],
    target_count: int
) -> list[dict]:
    """Fetch top artists from Deezer charts for specific genres."""
    all_artists = []
    seen_ids = set()

    for genre_id in genre_ids:
        try:
            # Fetch artists from genre chart
            # Deezer API: /genre/{id}/artists?limit=100
            data = await dz._request_with_retry(
                f"{dz.BASE}/genre/{genre_id}/artists",
                params={"limit": min(target_count, 100)}
            )

            if not data or "data" not in data:
                log.warning("[ARTISTS] No data returned for genre %d", genre_id)
                continue

            artists = data.get("data", [])
            if not artists:
                log.warning("[ARTISTS] Empty artist list for genre %d", genre_id)
                continue

            for artist in artists:
                artist_id = artist.get("id")
                if artist_id and artist_id not in seen_ids:
                    seen_ids.add(artist_id)
                    all_artists.append({
                        "id": artist_id,
                        "name": artist.get("name", ""),
                        "genre": genre_id
                    })

            log.info("[ARTISTS] Fetched %d artists from genre %d", len(artists), genre_id)

        except Exception as e:
            log.error("[ARTISTS] Failed to fetch genre %d: %s", genre_id, e)

    # Sort by artist ID (rough proxy for popularity on Deezer)
    all_artists.sort(key=lambda x: x["id"])

    # Return top N
    return all_artists[:target_count]


async def get_all_artist_tracks(
    dz: DeezerClient,
    artist_id: int,
    artist_name: str
) -> list[TrackInfo]:
    """Fetch ALL tracks for an artist by getting albums first, then tracks from each album."""
    all_tracks = []
    seen_track_ids = set()

    # Step 1: Get all albums for this artist
    albums = []
    page = 1
    page_size = 50

    while True:
        try:
            data = await dz._request_with_retry(
                f"{dz.BASE}/artist/{artist_id}/albums",
                params={"limit": page_size, "index": (page - 1) * page_size}
            )

            album_list = data.get("data", [])
            if not album_list:
                break

            albums.extend(album_list)

            # Check if we got fewer than requested (last page)
            if len(album_list) < page_size:
                break

            page += 1
            await asyncio.sleep(0.1)

        except Exception as e:
            log.error("[ALBUMS] Failed to fetch albums for %s (page %d): %s", artist_name, page, e)
            break

    log.info("[ALBUMS] Found %d albums for %s", len(albums), artist_name)

    # Step 2: Get tracks from each album
    for album in albums:
        album_id = album.get("id")
        album_title = album.get("title", "Unknown")

        if not album_id:
            continue

        album_page = 1
        while True:
            try:
                data = await dz._request_with_retry(
                    f"{dz.BASE}/album/{album_id}/tracks",
                    params={"limit": page_size, "index": (album_page - 1) * page_size}
                )

                track_list = data.get("data", [])
                if not track_list:
                    break

                for track_data in track_list:
                    track_id = track_data.get("id")
                    if track_id and track_id not in seen_track_ids:
                        seen_track_ids.add(track_id)
                        track = dz._parse_track(track_data)
                        all_tracks.append(track)

                # Check if we got fewer than requested (last page)
                if len(track_list) < page_size:
                    break

                album_page += 1
                await asyncio.sleep(0.1)

            except Exception as e:
                log.error("[TRACKS] Failed to fetch tracks from album %s for %s: %s",
                         album_title, artist_name, e)
                break

    log.info("[TRACKS] Fetched %d tracks for %s", len(all_tracks), artist_name)
    return all_tracks


# ═══════════════════════════════════════════════════
# Similar Songs Discovery
# ═══════════════════════════════════════════════════

async def find_similar_songs_for_track(
    track: TrackInfo,
    track_features: dict,
    dz: DeezerClient,
    lfm: Optional[LastfmClient],
    limit: int = 5
) -> list[TrackInfo]:
    """
    Find similar songs for a track (like the bot does).
    Uses Last.fm similar tracks + Deezer search.
    """
    similar_tracks = []
    seen_ids = {track.id}

    # Method 1: Last.fm similar tracks
    if lfm:
        try:
            lastfm_similar = await lfm.get_similar_tracks(
                track.artist, track.title, limit=limit * 2
            )

            for ls in lastfm_similar[:limit * 2]:
                if len(similar_tracks) >= limit:
                    break

                # Search on Deezer
                try:
                    results = await dz.search(f"{ls.name} {ls.artist}", limit=1)
                    if results and results[0].id not in seen_ids:
                        similar_tracks.append(results[0])
                        seen_ids.add(results[0].id)
                except Exception:
                    continue

                # Rate limiting
                await asyncio.sleep(0.1)

        except Exception as e:
            log.warning("[SIMILAR] Last.fm failed for %s: %s", track.title, e)

    # Method 2: Deezer artist top tracks (if not enough from Last.fm)
    if len(similar_tracks) < limit:
        try:
            artist_tracks = await dz.get_artist_top(track.artist_id, limit=limit)

            for t in artist_tracks:
                if len(similar_tracks) >= limit:
                    break
                if t.id not in seen_ids:
                    similar_tracks.append(t)
                    seen_ids.add(t.id)

        except Exception as e:
            log.warning("[SIMILAR] Deezer artist top failed for %s: %s", track.artist, e)

    # Method 3: Deezer search by genre (if still not enough)
    if len(similar_tracks) < limit and track.genres:
        try:
            genre = track.genres[0] if track.genres else ""
            if genre:
                results = await dz.search(genre, limit=limit)
                for t in results:
                    if len(similar_tracks) >= limit:
                        break
                    if t.id not in seen_ids:
                        similar_tracks.append(t)
                        seen_ids.add(t.id)
        except Exception:
            pass

    return similar_tracks[:limit]


# ═══════════════════════════════════════════════════
# Full Song Analysis
# ═══════════════════════════════════════════════════

async def full_song_analysis(
    track: TrackInfo,
    dz: DeezerClient,
    mb: MusicBrainzClient,
    lfm: Optional[LastfmClient]
) -> Optional[dict]:
    """
    Perform complete song analysis (like the bot does).
    Returns dict with all features.
    """
    track_id = track.id

    # Skip if already fully cached
    cached = await get_cached_features(track_id)
    if cached and (cached.get("audio_features") or cached.get("acoustic_features")):
        log.debug("[ANALYSIS] Skip (cached): %s - %s", track.artist, track.title)
        return cached

    log.info("[ANALYSIS] Analyzing: %s - %s (ID: %d)", track.artist, track.title, track_id)

    try:
        # Run analysis tasks in parallel
        audio_features = None
        acoustic_features = None
        musicbrainz_id = None
        lastfm_tags = []

        # Task 1: Audio analysis
        audio_task = None
        if track.preview_url:
            audio_task = analyze_audio(track.preview_url)

        # Task 2: MusicBrainz search
        mb_task = mb.search_recording(track.artist, track.title)

        # Task 3: Last.fm tags
        lastfm_task = None
        if lfm:
            lastfm_task = lfm.get_track_info(track.artist, track.title)

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

        # Handle Last.fm - get_track_info returns LastfmTrackInfo object
        if not isinstance(lastfm_result, Exception) and lastfm_result:
            # LastfmTrackInfo has a 'tags' attribute
            lastfm_tags = getattr(lastfm_result, 'tags', [])

        # Cache the results
        await cache_features(
            track_id, track.title, track.artist,
            audio_features, acoustic_features,
            musicbrainz_id, lastfm_tags
        )

        return {
            "audio_features": audio_features,
            "acoustic_features": acoustic_features,
            "musicbrainz_id": musicbrainz_id,
            "lastfm_tags": lastfm_tags
        }

    except Exception as e:
        log.error("[ANALYSIS] Failed for %s - %s: %s", track.artist, track.title, e)
        return None


# ═══════════════════════════════════════════════════
# Hourly Reporter
# ═══════════════════════════════════════════════════

async def send_hourly_report(
    report: HourlyReport,
    bot_token: str
):
    """Send hourly progress report via Telegram."""
    if not bot_token:
        log.warning("[REPORT] No bot token, skipping report")
        return

    try:
        import aiohttp

        # Format message
        message = f"""
📊 <b>Hourly Prefetch Report</b>
🕐 {report.timestamp}

🎤 <b>Artists Added ({len(report.artists_added)}):</b>
{chr(10).join(f"  • {name}" for name in report.artists_added[:10])}
{f"  ... and {len(report.artists_added) - 10} more" if len(report.artists_added) > 10 else ""}

🎵 <b>Songs Added:</b> {report.songs_added}
🔍 <b>Similar Songs Found:</b> {report.similar_songs_added}

💾 <b>Total Cached:</b> {report.total_cached:,} songs

❌ <b>Errors:</b> {report.errors}

📈 <b>Genre Breakdown:</b>
{chr(10).join(f"  • {genre}: {count} songs" for genre, count in report.genre_breakdown.items())}
"""

        # Send via Telegram API
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

            # Get bot info to find owner
            # For now, we'll log the report instead
            log.info("[REPORT] Hourly report:\n%s", message)

            # TODO: Store owner chat_id in config and send directly
            # For now, just log it

    except Exception as e:
        log.error("[REPORT] Failed to send report: %s", e)


# ═══════════════════════════════════════════════════
# Main Prefetch Loop
# ═══════════════════════════════════════════════════

async def prefetch_genre(
    genre_name: str,
    genre_config: dict,
    dz: DeezerClient,
    mb: MusicBrainzClient,
    lfm: Optional[LastfmClient],
    progress: PrefetchProgress
) -> HourlyReport:
    """Prefetch all artists for a specific genre."""
    artist_count = genre_config["artist_count"]
    genre_ids = genre_config["genre_ids"]

    log.info("=" * 60)
    log.info("[PREFETCH] Starting genre: %s (target: %d artists)", genre_name, artist_count)
    log.info("=" * 60)

    # Get top artists
    artists = await get_top_artists_by_genre(dz, genre_ids, artist_count)
    progress.artists_total = len(artists)
    progress.artists_completed = 0

    # Track hourly stats
    hourly_artists = []
    hourly_songs = 0
    hourly_similar = 0
    hourly_errors = 0
    hourly_start = time.time()

    # Process each artist
    for artist in artists:
        artist_id = artist["id"]
        artist_name = artist["name"]

        log.info("[ARTIST] Processing: %s (%d/%d)", artist_name,
                 progress.artists_completed + 1, progress.artists_total)

        try:
            # Get all tracks for this artist
            tracks = await get_all_artist_tracks(dz, artist_id, artist_name)

            if not tracks:
                log.warning("[ARTIST] No tracks found for %s", artist_name)
                progress.artists_completed += 1
                continue

            progress.songs_total += len(tracks)

            # Process each track
            for track in tracks:
                # Skip if already cached
                if await was_recently_prefetched(track.id, hours=24):
                    progress.songs_completed += 1
                    hourly_songs += 1
                    continue

                # Full analysis
                track_features = await full_song_analysis(track, dz, mb, lfm)

                if track_features:
                    # Find similar songs
                    similar = await find_similar_songs_for_track(
                        track, track_features, dz, lfm,
                        limit=SIMILAR_SONGS_PER_TRACK
                    )

                    # Analyze similar songs
                    for similar_track in similar:
                        if not await was_recently_prefetched(similar_track.id, hours=24):
                            await full_song_analysis(similar_track, dz, mb, lfm)
                            progress.similar_songs_found += 1
                            hourly_similar += 1

                progress.songs_completed += 1
                hourly_songs += 1

                # Rate limiting
                await asyncio.sleep(0.1)

            # Mark artist as completed
            progress.artists_completed += 1
            hourly_artists.append(artist_name)

            # Log progress
            log.info("[PROGRESS] %s: %d/%d artists, %d/%d songs",
                     genre_name,
                     progress.artists_completed, progress.artists_total,
                     progress.songs_completed, progress.songs_total)

        except Exception as e:
            log.error("[ARTIST] Failed for %s: %s", artist_name, e)
            progress.errors += 1
            hourly_errors += 1
            progress.artists_completed += 1

        # Check if we should send hourly report
        elapsed = time.time() - hourly_start
        if elapsed >= 3600:  # 1 hour
            # Create hourly report
            report = HourlyReport(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                artists_added=hourly_artists,
                songs_added=hourly_songs,
                similar_songs_added=hourly_similar,
                total_cached=progress.songs_completed,
                errors=hourly_errors,
                genre_breakdown={genre_name: hourly_songs}
            )

            # Send report
            await send_hourly_report(report, TELEGRAM_BOT_TOKEN)

            # Reset hourly counters
            hourly_artists = []
            hourly_songs = 0
            hourly_similar = 0
            hourly_errors = 0
            hourly_start = time.time()

    # Final report for this genre
    report = HourlyReport(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        artists_added=hourly_artists,
        songs_added=hourly_songs,
        similar_songs_added=hourly_similar,
        total_cached=progress.songs_completed,
        errors=hourly_errors,
        genre_breakdown={genre_name: hourly_songs}
    )

    return report


async def run_artist_prefetch():
    """Main prefetch execution for all genres."""
    log.info("=" * 80)
    log.info("ARTIST-BASED PREFETCH SYSTEM")
    log.info("=" * 80)
    log.info("Genres: %s", ", ".join(GENRE_TARGETS.keys()))
    log.info("Total artists: %d", sum(g["artist_count"] for g in GENRE_TARGETS.values()))
    log.info("Similar songs per track: %d", SIMILAR_SONGS_PER_TRACK)
    log.info("=" * 80)

    # Initialize clients
    dz = DeezerClient()
    mb = MusicBrainzClient()
    lfm = LastfmClient(LASTFM_API_KEY) if LASTFM_API_KEY else None

    try:
        # Initialize cache
        await init_cache()

        # Track overall progress
        overall_progress = PrefetchProgress(
            genre="all",
            start_time=time.time()
        )

        # Process each genre from Deezer
        for genre_name, genre_config in GENRE_TARGETS.items():
            progress = PrefetchProgress(
                genre=genre_name,
                start_time=time.time()
            )

            report = await prefetch_genre(
                genre_name, genre_config, dz, mb, lfm, progress
            )

            # Send genre completion report
            await send_hourly_report(report, TELEGRAM_BOT_TOKEN)

            # Update overall progress
            overall_progress.artists_completed += progress.artists_completed
            overall_progress.songs_completed += progress.songs_completed
            overall_progress.similar_songs_found += progress.similar_songs_found
            overall_progress.errors += progress.errors

        # Process Persian artists from database
        log.info("=" * 80)
        log.info("[PERSIAN] Starting Persian artist prefetch")
        log.info("=" * 80)

        persian_artists = await get_persian_artists(limit=PERSIAN_ARTISTS_COUNT)
        log.info("[PERSIAN] Found %d Persian artists to process", len(persian_artists))

        persian_progress = PrefetchProgress(
            genre="persian",
            start_time=time.time()
        )
        persian_progress.artists_total = len(persian_artists)

        for artist_info in persian_artists:
            artist_name = artist_info["name"]

            # Search for artist on Deezer
            deezer_artist = await search_artist_on_deezer(dz, artist_name)

            if not deezer_artist:
                log.warning("[PERSIAN] Artist not found on Deezer: %s", artist_name)
                persian_progress.artists_completed += 1
                continue

            # Get all tracks for this artist
            tracks = await get_all_artist_tracks(
                dz, deezer_artist["id"], artist_name
            )

            if not tracks:
                log.warning("[PERSIAN] No tracks found for %s", artist_name)
                persian_progress.artists_completed += 1
                continue

            persian_progress.songs_total += len(tracks)

            # Process each track
            for track in tracks:
                # Skip if already cached
                if await was_recently_prefetched(track.id, hours=24):
                    persian_progress.songs_completed += 1
                    continue

                # Full analysis
                track_features = await full_song_analysis(track, dz, mb, lfm)

                if track_features:
                    # Find similar songs
                    similar = await find_similar_songs_for_track(
                        track, track_features, dz, lfm,
                        limit=SIMILAR_SONGS_PER_TRACK
                    )

                    # Analyze similar songs
                    for similar_track in similar:
                        if not await was_recently_prefetched(similar_track.id, hours=24):
                            await full_song_analysis(similar_track, dz, mb, lfm)
                            persian_progress.similar_songs_found += 1

                persian_progress.songs_completed += 1

                # Rate limiting
                await asyncio.sleep(0.1)

            persian_progress.artists_completed += 1
            log.info("[PERSIAN] Completed %s (%d/%d artists, %d songs)",
                    artist_name,
                    persian_progress.artists_completed,
                    persian_progress.artists_total,
                    persian_progress.songs_completed)

        # Update overall progress
        overall_progress.artists_completed += persian_progress.artists_completed
        overall_progress.songs_completed += persian_progress.songs_completed
        overall_progress.similar_songs_found += persian_progress.similar_songs_found
        overall_progress.errors += persian_progress.errors

        # Final summary
        log.info("=" * 80)
        log.info("PREFETCH COMPLETE")
        log.info("=" * 80)
        log.info("Total artists: %d", overall_progress.artists_completed)
        log.info("Total songs: %d", overall_progress.songs_completed)
        log.info("Similar songs found: %d", overall_progress.similar_songs_found)
        log.info("Errors: %d", overall_progress.errors)
        log.info("Duration: %.1f hours", overall_progress.elapsed_hours())
        log.info("=" * 80)

        # Get final cache stats
        stats = await get_cache_stats()
        log.info("Final cache size: %d songs", stats.get("total_songs", 0))

    finally:
        # Cleanup
        await dz.close()
        await mb.close()
        if lfm:
            await lfm.close()


# ═══════════════════════════════════════════════════
# Continuous Mode
# ═══════════════════════════════════════════════════

async def run_continuous_prefetch(interval_hours: float = 24):
    """Run prefetch continuously, repeating every N hours."""
    log.info("[CONTINUOUS] Starting continuous prefetch (interval: %.1f hours)", interval_hours)

    while True:
        try:
            await run_artist_prefetch()
        except Exception as e:
            log.error("[CONTINUOUS] Prefetch failed: %s", e)

        log.info("[CONTINUOUS] Sleeping for %.1f hours...", interval_hours)
        await asyncio.sleep(interval_hours * 3600)


# ═══════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════

def main():
    """Command line interface."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Artist-based prefetch system"
    )
    parser.add_argument(
        "--genre",
        choices=list(GENRE_TARGETS.keys()) + ["all"],
        default="all",
        help="Genre to prefetch (default: all)"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=24,
        help="Interval for continuous mode in hours (default: 24)"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show cache statistics"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Run cleanup"
    )
    parser.add_argument(
        "--cleanup-days",
        type=int,
        default=30,
        help="Days old for cleanup (default: 30)"
    )
    parser.add_argument(
        "--list-genres",
        action="store_true",
        help="List available Deezer genres"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test with single artist"
    )

    args = parser.parse_args()

    if args.list_genres:
        async def show_genres():
            dz = DeezerClient()
            try:
                genres = await list_deezer_genres(dz)
                print("\n=== Available Deezer Genres ===")
                for g in sorted(genres, key=lambda x: x["id"]):
                    print(f"  {g['id']:3d}: {g['name']}")
                print(f"\nTotal: {len(genres)} genres")
                print("==============================\n")
            finally:
                await dz.close()

        asyncio.run(show_genres())

    elif args.test:
        async def test_single_artist():
            dz = DeezerClient()
            mb = MusicBrainzClient()
            lfm = LastfmClient(LASTFM_API_KEY) if LASTFM_API_KEY else None

            try:
                await init_cache()

                # Test with a known artist (Queen)
                test_artist = {"id": 412, "name": "Queen", "genre": 0}

                print(f"\n=== Testing with artist: {test_artist['name']} ===")

                # Get tracks
                tracks = await get_all_artist_tracks(dz, test_artist["id"], test_artist["name"])
                print(f"Found {len(tracks)} tracks")

                if tracks:
                    # Analyze first track
                    track = tracks[0]
                    print(f"\nAnalyzing: {track.title}")
                    result = await full_song_analysis(track, dz, mb, lfm)
                    if result:
                        print("[OK] Analysis complete")
                        print(f"  Audio features: {'Yes' if result.get('audio_features') else 'No'}")
                        print(f"  Acoustic features: {'Yes' if result.get('acoustic_features') else 'No'}")
                        print(f"  MusicBrainz ID: {result.get('musicbrainz_id', 'None')}")
                        print(f"  Last.fm tags: {len(result.get('lastfm_tags', []))}")

                        # Find similar songs
                        similar = await find_similar_songs_for_track(
                            track, result, dz, lfm, limit=3
                        )
                        print(f"\nFound {len(similar)} similar songs:")
                        for s in similar:
                            print(f"  * {s.artist} - {s.title}")
                    else:
                        print("[FAIL] Analysis failed")

                print("=============================\n")

            finally:
                await dz.close()
                await mb.close()
                if lfm:
                    await lfm.close()

        asyncio.run(test_single_artist())

    elif args.stats:
        async def show_stats():
            await init_cache()
            stats = await get_cache_stats()
            print("\n=== Cache Statistics ===")
            print(f"Total songs: {stats.get('total_songs', 0):,}")
            print(f"With audio features: {stats.get('with_audio', 0):,}")
            print(f"With acoustic features: {stats.get('with_acoustic', 0):,}")
            print(f"With MusicBrainz ID: {stats.get('with_mbid', 0):,}")
            print(f"With Last.fm tags: {stats.get('with_tags', 0):,}")
            print(f"Last 24h: {stats.get('recent_24h', 0):,}")
            print(f"Last 7 days: {stats.get('recent_7d', 0):,}")
            print("========================\n")

        asyncio.run(show_stats())

    elif args.cleanup:
        async def cleanup():
            await init_cache()
            removed = await cleanup_old_entries(args.cleanup_days)
            print(f"\n✓ Removed {removed} entries older than {args.cleanup_days} days\n")

        asyncio.run(cleanup())

    elif args.continuous:
        asyncio.run(run_continuous_prefetch(args.interval))

    elif args.genre != "all":
        # Prefetch single genre
        async def prefetch_single():
            dz = DeezerClient()
            mb = MusicBrainzClient()
            lfm = LastfmClient(LASTFM_API_KEY) if LASTFM_API_KEY else None

            try:
                await init_cache()

                progress = PrefetchProgress(
                    genre=args.genre,
                    start_time=time.time()
                )

                report = await prefetch_genre(
                    args.genre,
                    GENRE_TARGETS[args.genre],
                    dz, mb, lfm, progress
                )

                await send_hourly_report(report, TELEGRAM_BOT_TOKEN)

            finally:
                await dz.close()
                await mb.close()
                if lfm:
                    await lfm.close()

        asyncio.run(prefetch_single())

    else:
        # Run once for all genres
        asyncio.run(run_artist_prefetch())


if __name__ == "__main__":
    main()
