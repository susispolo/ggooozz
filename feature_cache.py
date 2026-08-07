"""
Feature cache using SQLite.
Stores analyzed audio features to avoid re-analysis.
"""
import json
import logging
from typing import Optional

import aiosqlite

from audio_analyzer import AudioFeatures
from musicbrainz_client import AcousticBrainzFeatures

log = logging.getLogger(__name__)

DB_PATH = "feature_cache.db"

# Connection pool for feature cache
_pool: aiosqlite.Connection | None = None


async def get_connection():
    """Get a database connection from the pool."""
    global _pool
    if _pool is None:
        _pool = await aiosqlite.connect(DB_PATH)
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def init_cache():
    """Initialize the feature cache database."""
    conn = await get_connection()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS track_features (
            track_id INTEGER PRIMARY KEY,
            title TEXT,
            artist TEXT,
            audio_features TEXT,
            acoustic_features TEXT,
            musicbrainz_id TEXT,
            lastfm_tags TEXT,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_artist_track ON track_features(title, artist)
    """)
    await conn.commit()
    log.info("Feature cache initialized")


async def get_cached_features(track_id: int) -> Optional[dict]:
    """
    Get cached features for a track.
    Returns dict with audio_features, acoustic_features, etc. or None.
    """
    log.debug("[CACHE] Looking up features for track ID: %d", track_id)

    conn = await get_connection()
    async with conn.execute(
        "SELECT audio_features, acoustic_features, musicbrainz_id, lastfm_tags FROM track_features WHERE track_id=?",
        (track_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            log.debug("[CACHE] Cache MISS for track ID: %d", track_id)
            return None

        audio_data, acoustic_data, mbid, tags_data = row

        log.info("[CACHE] Cache HIT for track ID: %d", track_id)

        audio_feat = None
        if audio_data:
            parsed = json.loads(audio_data)
            if isinstance(parsed, dict):
                audio_feat = AudioFeatures.from_dict(parsed)

        acoustic_feat = None
        if acoustic_data:
            parsed = json.loads(acoustic_data)
            if isinstance(parsed, dict):
                acoustic_feat = AcousticBrainzFeatures.from_dict(parsed)

        return {
            "audio_features": audio_feat,
            "acoustic_features": acoustic_feat,
            "musicbrainz_id": mbid,
            "lastfm_tags": json.loads(tags_data) if tags_data else [],
        }

async def cache_features(
    track_id: int,
    title: str,
    artist: str,
    audio_features: Optional[AudioFeatures] = None,
    acoustic_features: Optional[AcousticBrainzFeatures] = None,
    musicbrainz_id: Optional[str] = None,
    lastfm_tags: Optional[list[str]] = None,
):
    """Cache features for a track."""
    log.info("[CACHE] Saving features for: %s - %s (ID: %d)", artist, title, track_id)

    audio_json = json.dumps(audio_features.to_dict()) if audio_features else None
    acoustic_json = json.dumps(acoustic_features.to_dict()) if acoustic_features else None
    tags_json = json.dumps(lastfm_tags) if lastfm_tags else None

    conn = await get_connection()
    await conn.execute("""
        INSERT OR REPLACE INTO track_features
        (track_id, title, artist, audio_features, acoustic_features, musicbrainz_id, lastfm_tags)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (track_id, title, artist, audio_json, acoustic_json, musicbrainz_id, tags_json))
    await conn.commit()

    log.info("[CACHE] Saved successfully for: %s - %s", artist, title)

    # Auto-export to JSON for easy viewing (async, non-blocking)
    try:
        await export_cache_to_json()
    except Exception:
        pass  # Don't fail if export fails


async def get_or_analyze(
    track_id: int,
    title: str,
    artist: str,
    preview_url: str,
    analyzer_func,
    musicbrainz_func,
    lastfm_func,
) -> dict:
    """
    Get cached features or analyze and cache them.

    Returns dict with:
        - audio_features (AudioFeatures or None)
        - acoustic_features (AcousticBrainzFeatures or None)
        - musicbrainz_id (str or None)
        - lastfm_tags (list[str])
        - lastfm_match (float)
    """
    # Check cache first
    cached = await get_cached_features(track_id)
    if cached:
        log.info("Cache hit for track %d", track_id)
        return cached

    log.info("Cache miss for track %d, analyzing...", track_id)

    # Analyze audio
    audio_features = await analyzer_func(preview_url)

    # Get MusicBrainz ID and AcousticBrainz features
    musicbrainz_id = None
    acoustic_features = None
    mb_result = await musicbrainz_func(artist, title)
    if mb_result:
        musicbrainz_id = mb_result.get("musicbrainz_id")
        acoustic_features = mb_result.get("acoustic_features")

    # Get Last.fm tags
    lastfm_tags = []
    lastfm_match = 0.0
    if lastfm_func:
        lastfm_result = await lastfm_func(artist, title)
        if lastfm_result:
            lastfm_tags = lastfm_result.get("tags", [])
            lastfm_match = lastfm_result.get("match", 0.0)

    # Cache the results
    await cache_features(
        track_id, title, artist,
        audio_features, acoustic_features,
        musicbrainz_id, lastfm_tags,
    )

    return {
        "audio_features": audio_features,
        "acoustic_features": acoustic_features,
        "musicbrainz_id": musicbrainz_id,
        "lastfm_tags": lastfm_tags,
        "lastfm_match": lastfm_match,
    }


async def export_cache_to_json(filename: str = "cached_songs.json"):
    """Export all cached tracks to a JSON file for easy viewing."""
    conn = await get_connection()
    async with conn.execute(
        "SELECT track_id, title, artist, audio_features, acoustic_features, musicbrainz_id, lastfm_tags, analyzed_at FROM track_features"
    ) as cursor:
        rows = await cursor.fetchall()

    tracks = []
    for row in rows:
        track_id, title, artist, audio_data, acoustic_data, mbid, tags_data, analyzed_at = row

        track_info = {
            "track_id": track_id,
            "title": title,
            "artist": artist,
            "analyzed_at": analyzed_at,
            "musicbrainz_id": mbid,
        }

        # Parse audio features
        if audio_data:
            audio = json.loads(audio_data)
            track_info["bpm"] = audio.get("bpm", 0)
            track_info["key"] = audio.get("key", "")
            track_info["scale"] = audio.get("scale", "")
            track_info["energy"] = audio.get("rms_energy", 0)
            track_info["genre"] = audio.get("genre", "")
            track_info["mood"] = audio.get("mood", "")

        # Parse acoustic features
        if acoustic_data:
            acoustic = json.loads(acoustic_data)
            track_info["danceability"] = acoustic.get("danceability", 0)
            track_info["valence"] = acoustic.get("valence", 0)

        # Parse tags
        if tags_data:
            track_info["tags"] = json.loads(tags_data)

        tracks.append(track_info)

    # Write to file (using sync I/O in async context - fine for small writes)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(json.dumps(tracks, indent=2, ensure_ascii=False))

    log.debug("Exported %d tracks to %s", len(tracks), filename)
    return len(tracks)


async def was_recently_prefetched(track_id: int, hours: int = 24) -> bool:
    """Check if song was prefetched within the last N hours."""
    conn = await get_connection()
    async with conn.execute(
        """SELECT 1 FROM track_features
           WHERE track_id=? AND analyzed_at > datetime('now', ?)""",
        (track_id, f'-{hours} hours')
    ) as cursor:
        return await cursor.fetchone() is not None


async def get_cache_stats() -> dict:
    """Get statistics about the cache."""
    conn = await get_connection()

    stats = {}

    # Total songs
    async with conn.execute("SELECT COUNT(*) FROM track_features") as cursor:
        row = await cursor.fetchone()
        stats["total_songs"] = row[0] if row else 0

    # Songs with audio features
    async with conn.execute(
        "SELECT COUNT(*) FROM track_features WHERE audio_features IS NOT NULL"
    ) as cursor:
        row = await cursor.fetchone()
        stats["with_audio"] = row[0] if row else 0

    # Songs with acoustic features
    async with conn.execute(
        "SELECT COUNT(*) FROM track_features WHERE acoustic_features IS NOT NULL"
    ) as cursor:
        row = await cursor.fetchone()
        stats["with_acoustic"] = row[0] if row else 0

    # Songs with MusicBrainz ID
    async with conn.execute(
        "SELECT COUNT(*) FROM track_features WHERE musicbrainz_id IS NOT NULL"
    ) as cursor:
        row = await cursor.fetchone()
        stats["with_mbid"] = row[0] if row else 0

    # Songs with Last.fm tags
    async with conn.execute(
        "SELECT COUNT(*) FROM track_features WHERE lastfm_tags IS NOT NULL AND lastfm_tags != '[]'"
    ) as cursor:
        row = await cursor.fetchone()
        stats["with_tags"] = row[0] if row else 0

    # Recent additions (last 24h)
    async with conn.execute(
        "SELECT COUNT(*) FROM track_features WHERE analyzed_at > datetime('now', '-1 day')"
    ) as cursor:
        row = await cursor.fetchone()
        stats["recent_24h"] = row[0] if row else 0

    # Recent additions (last 7 days)
    async with conn.execute(
        "SELECT COUNT(*) FROM track_features WHERE analyzed_at > datetime('now', '-7 days')"
    ) as cursor:
        row = await cursor.fetchone()
        stats["recent_7d"] = row[0] if row else 0

    return stats


async def cleanup_old_entries(days_old: int = 30) -> int:
    """Remove cached entries older than N days.
    Returns number of entries removed.
    """
    conn = await get_connection()
    async with conn.execute(
        "DELETE FROM track_features WHERE analyzed_at < datetime('now', ?)",
        (f'-{days_old} days',)
    ) as cursor:
        removed = cursor.rowcount
    await conn.commit()
    return removed
