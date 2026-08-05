"""
Smoke test for Music Suggest Bot core logic.

Runs offline (no Telegram, no network). Exercises:
  1. DB init (user_prefs + feature_cache) with the real DB paths
  2. save_vote / get_user_votes round-trip
  3. add_to_user_playlist / get_user_taste_profile round-trip
  4. get_random_recommendations (from stored similar_tracks)
  5. AudioFeatures vector + similarity comparison
  6. Playlist energy-arc generation

Usage:
  venv/Scripts/python.exe tests/smoke_test.py
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_config import setup_logging
setup_logging(level=logging.INFO, log_file="")

import user_prefs
import feature_cache
from audio_analyzer import AudioFeatures
from similarity_engine import compare_audio_features, compute_weighted_similarity
from playlist_manager import generate_playlist, PlaylistTrack
from taste_profiler import build_taste_profile
from musicbrainz_client import AcousticBrainzFeatures

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


async def main():
    TEST_USER = 999999001  # unlikely to collide

    print("== 1. DB init ==")
    await user_prefs.init_db()
    await feature_cache.init_cache()
    check("user_prefs.init_db ok", os.path.exists("user_prefs.db"))
    check("feature_cache.init_cache ok", os.path.exists("feature_cache.db"))

    print("== 2. votes round-trip ==")
    await user_prefs.save_vote(TEST_USER, 3135556, "Bohemian Rhapsody", "Queen", 5)
    votes = await user_prefs.get_user_votes(TEST_USER, limit=10)
    check("vote saved", len(votes) >= 1, f"got {len(votes)}")
    stats = await user_prefs.get_user_rating_stats(TEST_USER)
    check("rating stats", stats["total_votes"] >= 1 and stats["avg_rating"] > 0, str(stats))

    print("== 3. user playlist + taste profile ==")
    await user_prefs.clear_user_playlist(TEST_USER)
    await user_prefs.add_to_user_playlist(
        TEST_USER, 3135556, "Bohemian Rhapsody", "Queen",
        bpm=144, energy=0.6, valence=0.35, genre="Rock", is_persian=False,
        similar_tracks=[3135557, 3135558, 3135559], original_text="Bohemian Rhapsody"
    )
    await user_prefs.add_to_user_playlist(
        TEST_USER, 111, "Some Persian Song", "Ebi",
        bpm=100, energy=0.4, valence=0.8, genre="Persian Pop", is_persian=True,
        similar_tracks=[222, 333], original_text="یه آهنگ"
    )
    playlist = await user_prefs.get_user_playlist(TEST_USER)
    check("user playlist has 2 tracks", len(playlist) == 2, f"got {len(playlist)}")

    profile = await user_prefs.get_user_taste_profile(TEST_USER)
    check("taste profile track_count==2", profile["track_count"] == 2, str(profile))
    check("taste profile persian_count==1", profile["persian_count"] == 1, str(profile))
    check("taste profile avg_bpm in range", 100 < profile["avg_bpm"] < 150, str(profile))

    print("== 4. random recommendations from similar pool ==")
    recs = await user_prefs.get_random_recommendations(TEST_USER, count=5)
    check("recommendations non-empty", len(recs) >= 1, f"got {recs}")

    print("== 5. feature vectors + similarity ==")
    a = AudioFeatures(bpm=120, rms_energy=0.5,
                      mfcc_mean=[0.1] * 13, chroma_mean=[0.05] * 12)
    b = AudioFeatures(bpm=122, rms_energy=0.52,
                      mfcc_mean=[0.11] * 13, chroma_mean=[0.05] * 12)
    c = AudioFeatures(bpm=60, rms_energy=0.05,
                      mfcc_mean=[0.9] * 13, chroma_mean=[0.8] * 12)
    sim_ab = compare_audio_features(a, b)
    sim_ac = compare_audio_features(a, c)
    check("similar tracks score high", sim_ab > 0.7, f"{sim_ab:.3f}")
    check("different tracks score low", sim_ac < sim_ab, f"{sim_ab:.3f} vs {sim_ac:.3f}")

    ac_a = AcousticBrainzFeatures(danceability=0.7, energy=0.6, valence=0.4)
    ac_b = AcousticBrainzFeatures(danceability=0.72, energy=0.61, valence=0.4)
    ac_c = AcousticBrainzFeatures(danceability=0.1, energy=0.1, valence=0.9)
    w1, brk1 = compute_weighted_similarity(a, b, ac_a, ac_b, lastfm_match=0.5)
    w2, brk2 = compute_weighted_similarity(a, c, ac_a, ac_c, lastfm_match=0.0)
    check("weighted sim higher for similar pair", w1 > w2, f"{w1:.3f} vs {w2:.3f}")

    print("== 6. playlist energy arc ==")
    tracks = [
        PlaylistTrack(track_id=i, title=f"S{i}", artist="A", energy=e, bpm=120)
        for i, e in enumerate([0.9, 0.1, 0.5, 0.8, 0.2, 0.6, 0.3, 0.7, 0.4])
    ]
    pl = await generate_playlist(
        {"track_id": 1, "title": "Seed", "artist": "A", "energy": 0.5, "bpm": 120, "preview_url": ""},
        [t.__dict__ for t in tracks[:8]], max_tracks=10,
    )
    check("playlist has tracks", len(pl) >= 1, f"got {len(pl)}")

    print("== 7. taste profile builder ==")
    tp = build_taste_profile([{"rating": 5}, {"rating": 3}], {})
    check("taste builder avg_rating==4.0", abs(tp.avg_rating - 4.0) < 0.01, str(tp.avg_rating))

    print(f"\n=== RESULT: {PASS} passed, {FAIL} failed ===")
    return 1 if FAIL else 0


if __name__ == "__main__":
    import logging
    sys.exit(asyncio.run(main()))
