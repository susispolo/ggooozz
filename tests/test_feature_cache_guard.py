"""Regression tests for feature_cache robustness.

The production bug: get_cached_features crashed with
"'NoneType' object has no attribute 'get'" when a track's audio_features
column held the JSON literal 'null' (or any non-object JSON). This happens
for Persian/Western tracks whose fast-mode analysis cached no audio.
"""
import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import feature_cache as fc

fc.DB_PATH = os.path.join(tempfile.mkdtemp(), "feat.db")

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


async def main():
    await fc.init_cache()

    # 1. Cache a row whose audio_features is the JSON literal 'null'
    import aiosqlite
    async with aiosqlite.connect(fc.DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO track_features (track_id, title, artist, audio_features,
               acoustic_features, musicbrainz_id, lastfm_tags)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (999001, "Test Song", "Test Artist", "null", None, None, "[]"),
        )
        await conn.commit()

    # 2. Reading it back must NOT crash, must return audio_features=None
    cached = await fc.get_cached_features(999001)
    check("null audio_features read returns dict", isinstance(cached, dict))
    check("null audio_features -> audio_features is None",
          cached.get("audio_features") is None)

    # 3. A row with a valid audio JSON still parses
    valid = {
        "bpm": 120.0, "rms_energy": 0.5, "key": "C", "scale": "major",
        "mfcc_mean": [0.1] * 13, "mfcc_var": [0.01] * 13,
    }
    async with aiosqlite.connect(fc.DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO track_features (track_id, title, artist, audio_features,
               acoustic_features, musicbrainz_id, lastfm_tags)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (999002, "Test Song 2", "Test Artist", json.dumps(valid), None, None, "[]"),
        )
        await conn.commit()

    cached2 = await fc.get_cached_features(999002)
    check("valid audio JSON parses", cached2.get("audio_features") is not None)
    check("valid audio BPM correct", cached2["audio_features"].bpm == 120.0)

    # 4. cache_features with None audio still round-trips (no crash)
    await fc.cache_features(999003, "Test Song 3", "Test Artist", None, None, None, [])
    cached3 = await fc.get_cached_features(999003)
    check("cache_features(None) round-trips", isinstance(cached3, dict))

    print(f"\n{'-'*40}\nPASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
