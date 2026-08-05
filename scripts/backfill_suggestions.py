"""Backfill the user_suggestions pool for existing playlist songs.

The per-user suggestion pool (user_suggestions) only fills when songs are
added AFTER the feature shipped. This script re-runs the similar-track lookup
(fallback chain: radio -> artist top -> artist search) for every existing
recognized song and stores the results, so "For Me" works immediately.

Usage:
    venv/Scripts/python.exe scripts/backfill_suggestions.py [--user 240082844]
    (without --user, backfills ALL users)
"""
import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_config import setup_logging
setup_logging(level=logging.INFO, log_file="bot.log")

import aiosqlite
from deezer_helper import DeezerClient
from user_prefs import DB_PATH, add_to_user_playlist  # noqa: F401 (import side effects)
from user_prefs import store_suggestions


async def backfill(user_id: int | None):
    dz = DeezerClient()
    async with aiosqlite.connect(DB_PATH) as conn:
        if user_id:
            query = """SELECT id, track_id, title, artist FROM user_playlist
                       WHERE user_id=? AND recognized=1 AND track_id > 0"""
            rows = await (await conn.execute(query, (user_id,))).fetchall()
        else:
            query = """SELECT id, track_id, title, artist FROM user_playlist
                       WHERE recognized=1 AND track_id > 0"""
            rows = await (await conn.execute(query)).fetchall()

    print(f"Found {len(rows)} recognized songs to process")
    total_new = 0
    total_empty = 0

    for i, (pid, track_id, title, artist) in enumerate(rows, 1):
        try:
            track = await dz.get_track(track_id)
            if not track:
                print(f"  [{i}/{len(rows)}] track {track_id} ({title}) -> no data")
                continue
            sims = await dz.get_similar(track_id, limit=5, track=track)
            ids = [s.id for s in sims]
            if ids:
                n = await store_suggestions(await _owner_of(pid, user_id), track_id, ids)
                total_new += n
                print(f"  [{i}/{len(rows)}] {title[:40]:42s} -> {len(ids)} similar ({n} new)")
            else:
                total_empty += 1
                print(f"  [{i}/{len(rows)}] {title[:40]:42s} -> 0 similar (skipped)")
        except Exception as e:
            print(f"  [{i}/{len(rows)}] {title[:40]:42s} -> ERROR {e}")

    await dz.close()
    print(f"\nDone. {total_new} new suggestions stored, {total_empty} songs yielded nothing.")


async def _owner_of(playlist_id: int, known_user: int | None) -> int:
    """Get the user_id owning a playlist row (needed for the all-users pass)."""
    if known_user:
        return known_user
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT user_id FROM user_playlist WHERE id=?", (playlist_id,))).fetchone()
    return row[0] if row else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", type=int, default=None, help="Only backfill this user (default: all)")
    args = ap.parse_args()
    asyncio.run(backfill(args.user))
