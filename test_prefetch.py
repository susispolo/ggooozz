#!/usr/bin/env python3
"""
Test script for prefetch system.
Run this to verify everything works before enabling in production.
"""

import asyncio
import sys
from feature_cache import init_cache, get_cache_stats
from prefetch_popular import run_prefetch


async def test_prefetch():
    """Test the prefetch system."""
    print("\n" + "=" * 60)
    print("PREFETCH SYSTEM TEST")
    print("=" * 60)

    # Initialize cache
    print("\n1. Initializing cache...")
    await init_cache()

    # Get initial stats
    print("2. Getting initial cache stats...")
    stats = await get_cache_stats()
    print(f"   Initial cache size: {stats['total_songs']} songs")

    # Run prefetch with small target
    print("\n3. Running prefetch (target: 5 songs)...")
    result = await run_prefetch(target_songs=5)
    print(f"   Fetched: {result.fetched}")
    print(f"   Skipped: {result.skipped}")
    print(f"   Errors: {result.errors}")

    # Get final stats
    print("\n4. Getting final cache stats...")
    stats = await get_cache_stats()
    print(f"   Final cache size: {stats['total_songs']} songs")
    print(f"   With audio features: {stats['with_audio']}")
    print(f"   With acoustic features: {stats['with_acoustic']}")
    print(f"   With MusicBrainz ID: {stats['with_mbid']}")
    print(f"   With Last.fm tags: {stats['with_tags']}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60 + "\n")

    return result


if __name__ == "__main__":
    try:
        result = asyncio.run(test_prefetch())
        sys.exit(0 if result.errors == 0 else 1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
