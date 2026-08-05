"""Tests for the per-user suggestion pool (user_suggestions table)."""
import asyncio
import os
import sys
import tempfile

# Use a temp DB so we never touch the real user_prefs.db
_TMPDIR = tempfile.mkdtemp(prefix="musicbot_sugg_")
os.environ["DB_PATH_OVERRIDE"] = _TMPDIR  # not used by user_prefs, see below

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# user_prefs reads DB_PATH at import time — patch it after import
import user_prefs as up

up.DB_PATH = os.path.join(_TMPDIR, "test.db")


async def run():
    await up.init_db()

    uid = 424242

    # 1) Store 5 suggestions for song A, 5 for song B (10 rows)
    n1 = await up.store_suggestions(uid, source_song_id=101, track_ids=[201, 202, 203, 204, 205])
    n2 = await up.store_suggestions(uid, source_song_id=102, track_ids=[206, 207, 208, 209, 210])
    assert n1 == 5, f"first store should add 5, got {n1}"
    assert n2 == 5, f"second store should add 5, got {n2}"

    # 2) Dedup: re-store overlapping IDs -> 0 new rows
    n3 = await up.store_suggestions(uid, source_song_id=103, track_ids=[201, 999])
    assert n3 == 1, f"overlap store should add only the new id (999), got {n3}"

    c = await up.count_suggestions(uid)
    assert c == 11, f"pool should have 11 unique rows, got {c}"

    # 3) Random sampling: 5 unique ids from the pool
    rows = await up.get_random_suggestions(uid, count=5)
    assert len(rows) == 5, f"should sample 5, got {len(rows)}"
    ids = [tid for tid, _ in rows]
    assert len(set(ids)) == len(ids), f"sampled ids must be unique, got {ids}"
    assert all(tid in {201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 999} for tid in ids), ids
    assert all(src in {101, 102, 103} for _, src in rows)

    # 4) Sampling more than pool size returns everything
    rows_all = await up.get_random_suggestions(uid, count=50)
    assert len(rows_all) == 11, f"oversample should return all 11, got {len(rows_all)}"

    # 5) Empty/invalid input is safe
    assert await up.store_suggestions(uid, 104, []) == 0
    assert await up.store_suggestions(uid, 104, [0, -3]) == 0
    assert await up.get_random_suggestions(999999) == []

    # 6) Per-user isolation: other user's pool is empty, our user unaffected
    assert await up.count_suggestions(888888) == 0

    # 7) Zero suggestion IDs (e.g. Deezer radio dead) stores nothing
    n4 = await up.store_suggestions(uid, 105, [])
    assert n4 == 0

    print(f"ALL SUGGESTION POOL TESTS PASSED (pool={c} rows)")


if __name__ == "__main__":
    asyncio.run(run())
