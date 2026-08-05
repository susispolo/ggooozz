"""
User preferences and data storage.
Handles votes, playlists, trivia scores, and listening history.
"""
import json
import logging
import random
import aiosqlite

log = logging.getLogger(__name__)

DB_PATH = "user_prefs.db"


async def init_db():
    """Initialize all database tables."""
    async with aiosqlite.connect(DB_PATH) as conn:
        # Votes table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                track_id INTEGER,
                track_title TEXT,
                track_artist TEXT,
                rating INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Playlists table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                track_ids TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Trivia scores table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trivia_scores (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                score INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0
            )
        """)

        # Listening history table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS listening_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                track_id INTEGER,
                track_title TEXT,
                track_artist TEXT,
                action TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # User playlist table (taste profile).
        # NOTE: uses CREATE IF NOT EXISTS (not DROP) so user data survives restarts.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_playlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                original_text TEXT,
                track_id INTEGER,
                title TEXT,
                artist TEXT,
                bpm REAL DEFAULT 0,
                energy REAL DEFAULT 0,
                valence REAL DEFAULT 0,
                genre TEXT DEFAULT '',
                is_persian INTEGER DEFAULT 0,
                similar_tracks TEXT DEFAULT '[]',
                language TEXT DEFAULT 'en',
                recognized INTEGER DEFAULT 1,
                release_year INTEGER DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: add any missing columns (schema evolved over time).
        await _migrate_add_columns(conn, "user_playlist", {
            "language": "TEXT DEFAULT 'en'",
            "recognized": "INTEGER DEFAULT 1",
            "release_year": "INTEGER DEFAULT 0",
        })

        await conn.commit()
    log.info("[USER_DB] init_db: tables created; PATH=%s", DB_PATH)


async def _migrate_add_columns(conn, table: str, columns: dict):
    """Add missing columns to an existing table (safe migration for old DBs)."""
    async with conn.execute(f"PRAGMA table_info({table})") as cursor:
        existing = {row[1] for row in await cursor.fetchall()}
    for col, ddl in columns.items():
        if col not in existing:
            try:
                await conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                log.info("[USER_DB] migration: added column %s.%s", table, col)
            except Exception as e:
                log.warning("[USER_DB] migration: could not add %s.%s: %s", table, col, e)


# ═══════════════════════════════════════════════════
# Votes
# ═══════════════════════════════════════════════════

async def save_vote(user_id: int, track_id: int, title: str, artist: str, rating: int):
    log.info("[VOTE] save user=%s track=%s (%s - %s) rating=%s", user_id, track_id, title, artist, rating)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO votes (user_id, track_id, track_title, track_artist, rating) VALUES (?, ?, ?, ?, ?)",
            (user_id, track_id, title, artist, rating),
        )
        await conn.commit()
    log.info("[VOTE] saved OK user=%s track=%s", user_id, track_id)


async def get_track_avg_rating(track_id: int) -> float:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT AVG(rating) FROM votes WHERE track_id=?", (track_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else 0.0


async def get_user_votes(user_id: int, limit: int = 20) -> list:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT track_title, track_artist, rating FROM votes WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
    log.info("[VOTE] get_user_votes user=%s limit=%s -> %d rows", user_id, limit, len(rows))
    return rows


async def get_user_rating_stats(user_id: int) -> dict:
    """Get user's rating statistics."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT AVG(rating), COUNT(*), MIN(rating), MAX(rating) FROM votes WHERE user_id=?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
    stats = {
        "avg_rating": row[0] if row[0] else 0.0,
        "total_votes": row[1] if row[1] else 0,
        "min_rating": row[2] if row[2] else 0,
        "max_rating": row[3] if row[3] else 0,
    }
    log.info("[VOTE] get_user_rating_stats user=%s -> %s", user_id, stats)
    return stats


async def get_user_top_artists(user_id: int, limit: int = 5) -> list:
    """Get user's most rated artists."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            """SELECT track_artist, COUNT(*) as count, AVG(rating) as avg_rating
               FROM votes WHERE user_id=?
               GROUP BY track_artist
               ORDER BY count DESC
               LIMIT ?""",
            (user_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
    log.info("[VOTE] get_user_top_artists user=%s -> %d artists", user_id, len(rows))
    return rows


# ═══════════════════════════════════════════════════
# Playlists
# ═══════════════════════════════════════════════════

async def save_playlist(user_id: int, name: str, track_ids: list[int]) -> int:
    """Save a playlist and return its ID."""
    log.info("[PLAYLIST] save_playlist user=%s name=%r tracks=%d", user_id, name, len(track_ids))
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "INSERT INTO playlists (user_id, name, track_ids) VALUES (?, ?, ?)",
            (user_id, name, json.dumps(track_ids))
        )
        await conn.commit()
    log.info("[PLAYLIST] saved OK id=%s user=%s", cursor.lastrowid, user_id)
    return cursor.lastrowid


async def get_user_playlists(user_id: int) -> list:
    """Get all playlists for a user."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT id, name, track_ids, created_at FROM playlists WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            playlists = [{"id": r[0], "name": r[1], "track_ids": json.loads(r[2]), "created_at": r[3]} for r in rows]
    log.info("[PLAYLIST] get_user_playlists user=%s -> %d playlists", user_id, len(playlists))
    return playlists


async def get_playlist(playlist_id: int) -> dict:
    """Get a playlist by ID."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT id, user_id, name, track_ids, created_at FROM playlists WHERE id=?",
            (playlist_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"id": row[0], "user_id": row[1], "name": row[2], "track_ids": json.loads(row[3]), "created_at": row[4]}
            return None


# ═══════════════════════════════════════════════════
# Trivia
# ═══════════════════════════════════════════════════

async def update_trivia_score(user_id: int, username: str, points: int, won: bool):
    """Update trivia score for a user."""
    log.info("[TRIVIA_DB] update user=%s name=%s points=%s won=%s", user_id, username, points, won)
    async with aiosqlite.connect(DB_PATH) as conn:
        # Check if user exists
        async with conn.execute("SELECT score, games_played, streak, best_streak FROM trivia_scores WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()

        if row:
            new_score = row[0] + points
            new_games = row[1] + 1
            new_streak = row[2] + 1 if won else 0
            new_best = max(row[3], new_streak)
            await conn.execute(
                "UPDATE trivia_scores SET score=?, games_played=?, streak=?, best_streak=?, username=? WHERE user_id=?",
                (new_score, new_games, new_streak, new_best, username, user_id)
            )
        else:
            await conn.execute(
                "INSERT INTO trivia_scores (user_id, username, score, games_played, streak, best_streak) VALUES (?, ?, ?, 1, ?, ?)",
                (user_id, username, points, 1 if won else 0, 1 if won else 0)
            )
        await conn.commit()


async def get_trivia_leaderboard(limit: int = 10) -> list:
    """Get top trivia players."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT username, score, games_played, best_streak FROM trivia_scores ORDER BY score DESC LIMIT ?",
            (limit,)
        ) as cursor:
            return await cursor.fetchall()


async def get_trivia_stats(user_id: int) -> dict:
    """Get trivia stats for a user."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT score, games_played, streak, best_streak FROM trivia_scores WHERE user_id=?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"score": row[0], "games": row[1], "streak": row[2], "best_streak": row[3]}
            return {"score": 0, "games": 0, "streak": 0, "best_streak": 0}


# ═══════════════════════════════════════════════════
# Listening History
# ═══════════════════════════════════════════════════

async def add_to_history(user_id: int, track_id: int, title: str, artist: str, action: str = "search"):
    """Add a track to user's listening history."""
    log.info("[HIST] add_to_history user=%s track=%s (%s - %s) action=%s", user_id, track_id, title, artist, action)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO listening_history (user_id, track_id, track_title, track_artist, action) VALUES (?, ?, ?, ?, ?)",
            (user_id, track_id, title, artist, action)
        )
        await conn.commit()
    log.info("[HIST] added OK user=%s track=%s", user_id, track_id)


async def get_user_history(user_id: int, limit: int = 20) -> list:
    """Get user's listening history."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT track_title, track_artist, action, created_at FROM listening_history WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
    log.info("[HIST] get_user_history user=%s -> %d rows", user_id, len(rows))
    return rows


# ═══════════════════════════════════════════════════
# Global Stats
# ═══════════════════════════════════════════════════

async def get_top_rated_tracks(limit: int = 10) -> list:
    """Get globally top rated tracks."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            """SELECT track_title, track_artist, AVG(rating) as avg_rating, COUNT(*) as vote_count
               FROM votes
               GROUP BY track_id
               HAVING vote_count >= 2
               ORDER BY avg_rating DESC, vote_count DESC
               LIMIT ?""",
            (limit,)
        ) as cursor:
            return await cursor.fetchall()


async def get_most_active_users(limit: int = 10) -> list:
    """Get most active users by vote count."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            """SELECT user_id, COUNT(*) as vote_count, AVG(rating) as avg_rating
               FROM votes
               GROUP BY user_id
               ORDER BY vote_count DESC
               LIMIT ?""",
            (limit,)
        ) as cursor:
            return await cursor.fetchall()


# ═══════════════════════════════════════════════════
# User Playlist (Taste Profile)
# ═══════════════════════════════════════════════════

async def add_to_user_playlist(user_id: int, track_id: int, title: str, artist: str,
                               bpm: float = 0, energy: float = 0, valence: float = 0,
                               genre: str = '', is_persian: bool = False,
                               similar_tracks: list = None, original_text: str = '',
                               language: str = 'en', recognized: bool = True,
                               release_year: int = 0):
    """Add a track to user's playlist. Idempotent: skips if the same track
    (same track_id, or same title+artist for unrecognized songs) already exists
    for this user, so re-sending a batch doesn't duplicate rows."""
    similar_json = json.dumps(similar_tracks) if similar_tracks else '[]'
    # Backward-compat: if is_persian is set but no explicit language, default to fa
    if is_persian and (not language or language == 'en'):
        language = 'fa'

    async with aiosqlite.connect(DB_PATH) as conn:
        # Dedup check: same user + same track_id (for recognized), or
        # same user + same title (for unrecognized, track_id=0).
        if track_id and track_id > 0:
            async with conn.execute(
                "SELECT id FROM user_playlist WHERE user_id=? AND track_id=? AND track_id > 0",
                (user_id, track_id)
            ) as cursor:
                existing = await cursor.fetchone()
        else:
            async with conn.execute(
                "SELECT id FROM user_playlist WHERE user_id=? AND title=? AND track_id=0",
                (user_id, title)
            ) as cursor:
                existing = await cursor.fetchone()

        if existing:
            log.info("[PLAYLIST_DB] duplicate skipped user=%s track=%s (%s - %s)",
                     user_id, track_id, title, artist)
            return False

        await conn.execute(
            """INSERT INTO user_playlist
               (user_id, original_text, track_id, title, artist, bpm, energy, valence, genre, is_persian, similar_tracks, language, recognized, release_year)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, original_text, track_id, title, artist, bpm, energy, valence, genre, 1 if is_persian else 0,
             similar_json, language, 1 if recognized else 0, release_year)
        )
        await conn.commit()
    log.info("[PLAYLIST_DB] added OK user=%s track=%s (%s - %s) lang=%s year=%s",
             user_id, track_id, title, artist, language, release_year)
    return True


async def get_user_playlist(user_id: int) -> list:
    """Get all tracks in user's playlist."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            """SELECT id, original_text, track_id, title, artist, bpm, energy, valence, genre, is_persian, similar_tracks, language, recognized, release_year, added_at
               FROM user_playlist
               WHERE user_id=?
               ORDER BY added_at DESC""",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
    log.info("[PLAYLIST_DB] get_user_playlist user=%s -> %d rows", user_id, len(rows))
    return rows


async def clear_user_playlist(user_id: int):
    """Clear all tracks from user's playlist."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("DELETE FROM user_playlist WHERE user_id=?", (user_id,))
        await conn.commit()


async def get_user_taste_profile(user_id: int) -> dict:
    """Calculate user's taste profile from playlist.

    Only RECOGNIZED tracks (recognized=1) are included in audio/genre/language
    analysis. Unrecognized songs count toward total but not the taste data.
    """
    log.info("[PLAYLIST_DB] get_user_taste_profile user=%s", user_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        # Overall total (all songs incl. unrecognized)
        async with conn.execute(
            "SELECT COUNT(*) FROM user_playlist WHERE user_id=?", (user_id,)
        ) as cursor:
            total_count = (await cursor.fetchone())[0] or 0

        # Recognized-only stats
        async with conn.execute(
            """SELECT AVG(bpm), AVG(energy), AVG(valence), COUNT(*)
               FROM user_playlist
               WHERE user_id=? AND recognized=1 AND bpm > 0""",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            avg_bpm = row[0] or 0
            avg_energy = row[1] or 0
            avg_valence = row[2] or 0
            track_count = row[3] or 0

        # Recognized count (songs with real analysis data)
        async with conn.execute(
            "SELECT COUNT(*) FROM user_playlist WHERE user_id=? AND recognized=1", (user_id,)
        ) as cursor:
            recognized_count = (await cursor.fetchone())[0] or 0

        # Genre stats (recognized only)
        async with conn.execute(
            """SELECT genre, COUNT(*) as count
               FROM user_playlist
               WHERE user_id=? AND recognized=1 AND genre != ''
               GROUP BY genre
               ORDER BY count DESC""",
            (user_id,)
        ) as cursor:
            genre_rows = await cursor.fetchall()
            genres = {row[0]: row[1] for row in genre_rows}

        # Language stats (all languages, recognized only)
        async with conn.execute(
            """SELECT language, COUNT(*) as count
               FROM user_playlist
               WHERE user_id=? AND recognized=1
               GROUP BY language
               ORDER BY count DESC""",
            (user_id,)
        ) as cursor:
            lang_rows = await cursor.fetchall()
            languages = {row[0]: row[1] for row in lang_rows}

        # Era stats (recognized tracks with a release year)
        async with conn.execute(
            """SELECT release_year
               FROM user_playlist
               WHERE user_id=? AND recognized=1 AND release_year > 0""",
            (user_id,)
        ) as cursor:
            year_rows = await cursor.fetchall()
            years = [r[0] for r in year_rows]

        # Keep is_persian/english for backward-compat callers
        persian_count = languages.get("fa", 0)
        english_count = languages.get("en", 0)

        result = {
            "total_count": total_count,
            "recognized_count": recognized_count,
            "track_count": track_count,
            "avg_bpm": avg_bpm,
            "avg_energy": avg_energy,
            "avg_valence": avg_valence,
            "genres": genres,
            "languages": languages,
            "years": years,
            "persian_count": persian_count,
            "english_count": english_count,
        }

    log.info("[PLAYLIST_DB] taste_profile user=%s -> total=%d recognized=%d tracks=%d bpm=%.1f energy=%.2f valence=%.2f genres=%s langs=%s",
             user_id, total_count, recognized_count, track_count, avg_bpm, avg_energy, avg_valence,
             list(genres.keys())[:5], list(languages.items())[:8])
    return result


async def get_user_playlist_artists(user_id: int, limit: int = 5) -> list:
    """Get top artists in user's playlist."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            """SELECT artist, COUNT(*) as count
               FROM user_playlist
               WHERE user_id=?
               GROUP BY artist
               ORDER BY count DESC
               LIMIT ?""",
            (user_id, limit)
        ) as cursor:
            return await cursor.fetchall()


async def get_all_similar_tracks(user_id: int) -> list:
    """Get all similar tracks from user's playlist for recommendations."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            """SELECT similar_tracks FROM user_playlist
               WHERE user_id=? AND similar_tracks != '[]'""",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()

    all_similar = []
    for row in rows:
        if row[0]:
            try:
                tracks = json.loads(row[0])
                all_similar.extend(tracks)
            except Exception as e:
                log.warning("[PLAYLIST_DB] get_all_similar_tracks: bad JSON in row for user=%s: %s", user_id, e)

    log.info("[PLAYLIST_DB] get_all_similar_tracks user=%s -> %d similar track ids (from %d rows)",
             user_id, len(all_similar), len(rows))
    return all_similar


async def get_random_recommendations(user_id: int, count: int = 5) -> list:
    """Get random recommendations from user's similar tracks pool."""
    all_similar = await get_all_similar_tracks(user_id)

    if not all_similar:
        log.info("[PLAYLIST_DB] get_random_recommendations user=%s -> none available", user_id)
        return []

    # Remove duplicates and pick random
    unique_tracks = list(set(all_similar))
    if len(unique_tracks) <= count:
        log.info("[PLAYLIST_DB] get_random_recommendations user=%s -> %d (all unique)", user_id, len(unique_tracks))
        return unique_tracks

    picked = random.sample(unique_tracks, count)
    log.info("[PLAYLIST_DB] get_random_recommendations user=%s -> %d sampled from %d unique", user_id, len(picked), len(unique_tracks))
    return picked


async def search_tracks_by_features(bpm: float, energy: float, valence: float, limit: int = 10) -> list:
    """Search cached tracks by similar features."""
    async with aiosqlite.connect(DB_PATH) as conn:
        # This is a simplified search - in production you'd use cosine similarity
        async with conn.execute(
            """SELECT track_id, title, artist, bpm, energy, valence
               FROM cached_tracks
               WHERE ABS(bpm - ?) < 20
               AND ABS(energy - ?) < 0.1
               ORDER BY ABS(bpm - ?) + ABS(energy - ?) + ABS(valence - ?)
               LIMIT ?""",
            (bpm, energy, bpm, energy, valence, limit)
        ) as cursor:
            return await cursor.fetchall()
