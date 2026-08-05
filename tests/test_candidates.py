"""
Test the candidate-gathering + ranking logic from bot.handle_callback in isolation,
using a clean (non-live) track via Last.fm primary + Deezer search.
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
from lastfm_client import LastfmClient
from config import LASTFM_API_KEY
import bot


async def main():
    t0 = time.time()
    dz = bot.dz  # reuse the module's client
    lfm = bot.lfm
    await feature_cache.init_cache()

    # Search a clean, well-known track
    results = await dz.search("mr brightside the killers", limit=3)
    track = next((t for t in results if t.preview_url and "live" not in t.title.lower()), results[0])
    print(f"\nSELECTED: {track.title} - {track.artist} (id={track.id})")

    # 1. Last.fm similar
    lfm_sim = await lfm.get_similar_tracks(track.artist, track.title, limit=8) if lfm else []
    print(f"\nLast.fm similar ({len(lfm_sim)}):")
    for s in lfm_sim[:6]:
        print(f"  {s.match:.2f}  {s.name} - {s.artist}")

    # 2. Simulate the bot's candidate gathering (Last.fm primary -> Deezer lookup)
    diff = []
    seen = {track.title.lower()}
    for ls in lfm_sim[:8]:
        r = await dz.search(f"{ls.name} {ls.artist}", limit=1)
        if r:
            t = r[0]
            if t.artist_id != track.artist_id and t.title.lower() not in seen:
                t.lastfm_match = ls.match
                diff.append((t, ls.match))
                seen.add(t.title.lower())
    print(f"\nDifferent-artist candidates (by Deezer lookup): {len(diff)}")
    for t, m in sorted(diff, key=lambda x: x[1], reverse=True)[:6]:
        print(f"  {m:.2f}  {t.title} - {t.artist}")

    # 3. If none (means track has no diverse Last.fm results), fall back to artist top
    if not diff:
        at = await dz.get_artist_top(track.artist_id, limit=6)
        print(f"\nFallback artist top: {len(at)}")

    print(f"\nDONE in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())