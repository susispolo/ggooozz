"""
Live pipeline test: analyze a real song and rank similar tracks.
This exercises the actual recommendation path (network + librosa + caches).

Usage: venv/Scripts/python.exe tests/live_analysis_test.py
"""
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_config import setup_logging
setup_logging(level=logging.INFO, log_file="")

import feature_cache
from deezer_helper import DeezerClient
from musicbrainz_client import MusicBrainzClient
from lastfm_client import LastfmClient
from config import LASTFM_API_KEY


async def main():
    t0 = time.time()
    dz = DeezerClient()
    mb = MusicBrainzClient()
    lfm = LastfmClient(LASTFM_API_KEY) if LASTFM_API_KEY else None

    try:
        await feature_cache.init_cache()

        print("\n=== SEARCH (clean-first) ===")
        results = await dz.search("queen bohemian rhapsody", limit=5)
        live_markers = ("live", "remaster", "remix", "edit", "version", "deluxe", "reissue")
        clean = [t for t in results if not any(m in t.title.lower() for m in live_markers)]
        results = clean + [t for t in results if any(m in t.title.lower() for m in live_markers)]
        for t in results[:5]:
            print(f"  [{ 'CLEAN' if t in clean else 'live '}] {t.title} - {t.artist} (id={t.id})")
        track = results[0] if results else None
        if not track:
            print("[FAIL] no search results")
            return 1
        print(f"Selected: {track.title} - {track.artist} (id={track.id}, preview={bool(track.preview_url)})")

        print("\n=== FULL TRACK ===")
        full = await dz.get_track(track.id)
        if full:
            print(f"  genres={full.genres} preview={bool(full.preview_url)}")

        print("\n=== ANALYZE TARGET (librosa + MB + Last.fm) ===")
        from bot import analyze_track
        f = await analyze_track(track)
        af = f.get("audio_features")
        ac = f.get("acoustic_features")
        print(f"  audio_features: {'OK' if af else 'MISSING'}  (bpm={af.bpm if af else None})")
        print(f"  acoustic_features: {'OK' if ac else 'MISSING'} (dance={ac.danceability if ac else None})")
        print(f"  lastfm_tags: {f.get('lastfm_tags')}")

        print("\n=== GET SIMILAR + RANK ===")
        similar = await dz.get_similar(track.id, limit=6) or (await dz.get_artist_top(track.artist_id, limit=6))
        print(f"  similar candidates: {len(similar)}")
        if not similar:
            print("[WARN] no similar candidates")
            return 0

        from bot import find_similar_tracks
        ranked = await find_similar_tracks(track, f, similar)
        for r in ranked[:6]:
            print(f"  {r.similarity_score:.2f}  {r.title} - {r.artist}")

        print(f"\n=== DONE in {time.time()-t0:.1f}s ===")
        return 0
    finally:
        await dz.close()
        await mb.close()
        if lfm:
            await lfm.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))