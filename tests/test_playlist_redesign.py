"""
Test for the playlist redesign: migration, language detection, add-to-playlist
with recognized/unrecognized, and taste profile stats.
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_config import setup_logging
setup_logging(level=logging.INFO, log_file="")

import user_prefs
from language_detect import detect_language, language_label

TEST_USER = 999999002


async def main():
    print("== 1. Migration on existing DB ==")
    await user_prefs.init_db()  # real DB, has old schema/songs
    async with __import__("aiosqlite").connect(user_prefs.DB_PATH) as conn:
        cur = await conn.execute("PRAGMA table_info(user_playlist)")
        cols = [r[1] for r in await cur.fetchall()]
        print("  columns:", cols)
        assert "language" in cols and "recognized" in cols and "release_year" in cols, "migration failed"
        print("  [PASS] new columns exist")

    print("\n== 2. Old rows preserved + defaults ==")
    async with __import__("aiosqlite").connect(user_prefs.DB_PATH) as conn:
        cur = await conn.execute("SELECT COUNT(*), COUNT(language), COUNT(recognized) FROM user_playlist")
        total, lang, rec = await cur.fetchone()
        print(f"  total={total}, lang-filled={lang}, recognized-filled={rec}")
        assert total > 0, "old data lost!"
        print("  [PASS] old rows survived migration")

    print("\n== 3. Language detection ==")
    cases = [
        (("Saaltak Habiby", "Fairuz", "Fairuz  Saaltak Habiby"), "ar"),
        (("Dynamite", "BTS", "BTS - Dynamite"), "ko"),
        (("What Makes A Good Man?", "The Heavy", "The Heavy What Makes A Good Man?"), "en"),
        (("Wa Habibi", "Fairuz", "Fairuz Wa Habibi"), "ar"),
    ]
    for (t, a, o), exp in cases:
        got = detect_language(t, a, o)
        status = "PASS" if got == exp else "FAIL"
        print(f"  [{status}] {t!r} - {a!r} -> {got} (exp {exp})")
        assert got == exp

    print("\n== 4. add recognized + unrecognized ==")
    await user_prefs.init_db()
    await user_prefs.clear_user_playlist(TEST_USER)
    # recognized (real)
    await user_prefs.add_to_user_playlist(TEST_USER, 111, "Bohemian Rhapsody", "Queen",
                                          bpm=144, energy=0.6, valence=0.4, genre="Rock",
                                          similar_tracks=[1, 2, 3], language="en", recognized=True, release_year=1975)
    # recognized (Fairuz -> Arabic)
    await user_prefs.add_to_user_playlist(TEST_USER, 222, "Wa Habibi", "Fairuz",
                                          bpm=172, energy=0.5, valence=0.6, genre="Arabic",
                                          similar_tracks=[4, 5], language="ar", recognized=True, release_year=1977)
    # unrecognized
    await user_prefs.add_to_user_playlist(TEST_USER, 0, "Some Song I Cant Find", "",
                                          original_text="Some Song I Cant Find",
                                          language="en", recognized=False)

    playlist = await user_prefs.get_user_playlist(TEST_USER)
    print(f"  playlist rows: {len(playlist)}")
    assert len(playlist) == 3
    print("  [PASS] 3 rows (2 recognized + 1 unrecognized)")

    print("\n== 5. Taste profile (excludes unrecognized) ==")
    profile = await user_prefs.get_user_taste_profile(TEST_USER)
    print("  profile:", {k: v for k, v in profile.items() if k not in ("years",)})
    assert profile["total_count"] == 3, "total should count all"
    assert profile["recognized_count"] == 2, "recognized should be 2"
    assert profile["track_count"] == 2, "audio analysis excludes unrecognized"
    assert profile["languages"] == {"en": 1, "ar": 1}, f"languages={profile['languages']}"
    print("  [PASS] stats correct")

    print("\n== 6. Myplaylist message shape ==")
    # simulate what cmd_myplaylist builds
    langs = profile["languages"]
    lines = []
    for code, count in sorted(langs.items(), key=lambda x: x[1], reverse=True):
        name, flag = language_label(code)
        lines.append(f"  {flag} {name}: {count}")
    print("  " + "\n  ".join(lines))

    print("\n=== ALL PLAYLIST TESTS PASSED ===")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))