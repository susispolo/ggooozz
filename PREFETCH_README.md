# Prefetch System for Music Suggest Bot

## Overview

The prefetch system automatically fetches and caches audio features for popular songs **before** users request them. This dramatically improves response times from 10-30 seconds to under 1 second for cached songs.

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│  BACKGROUND SCHEDULER (every 60 seconds)                │
│  ├─ Fetch top songs from Deezer charts                  │
│  ├─ Check if already cached (skip if yes)               │
│  ├─ For each new song:                                  │
│  │   ├─ Download 30s preview MP3                        │
│  │   ├─ Extract audio features (librosa)                │
│  │   ├─ Fetch MusicBrainz/AcousticBrainz features       │
│  │   ├─ Fetch Last.fm tags                              │
│  │   └─ Save to feature_cache.db                        │
│  └─ Log progress                                        │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  USER REQUEST                                           │
│  ├─ Search for song                                     │
│  ├─ Check cache (instant)                               │
│  ├─ Return pre-computed features                        │
│  └─ Response in <1 sec instead of 10-30 sec             │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### Option 1: Automatic (Recommended)

The prefetch scheduler starts automatically when you run the bot:

```bash
python bot.py
```

The scheduler runs in a background thread and:
- Fetches 15 popular songs every 60 seconds
- Runs cleanup once daily at 3 AM (removes entries older than 30 days)
- Logs to both console and `prefetch.log`

### Option 2: Manual Execution

Run the prefetch script manually:

```bash
# Fetch 15 songs (default)
python prefetch_popular.py

# Fetch custom number of songs
python prefetch_popular.py --target 20

# Run cleanup only
python prefetch_popular.py --cleanup

# Show cache statistics
python prefetch_popular.py --stats
```

### Option 3: Cron Job (Linux/Mac)

For more control, use system cron:

```bash
# Edit crontab
crontab -e

# Add line (runs every minute)
* * * * * cd /path/to/music-suggest-bot && python prefetch_popular.py >> prefetch.log 2>&1

# Add cleanup job (runs daily at 3 AM)
0 3 * * * cd /path/to/music-suggest-bot && python prefetch_popular.py --cleanup >> prefetch.log 2>&1
```

### Option 4: Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Every 1 minute
4. Set action: Start program
   - Program: `python`
   - Arguments: `D:\music-suggest-bot\prefetch_popular.py`

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Enable/disable prefetch scheduler (default: true)
ENABLE_PREFETCH=true

# Optional: Last.fm API key for better recommendations
LASTFM_API_KEY=your_key_here
```

### Configuration Constants

Edit `prefetch_popular.py` to customize:

```python
# Target songs per prefetch run
TARGET_SONGS_PER_RUN = 15  # Safe for rate limits

# Minimum hours before re-fetching a song
MIN_CACHE_HOURS = 24

# Persian genre ID on Deezer
PERSIAN_GENRE_ID = 196
```

## Data Sources

The prefetcher fetches from multiple sources for variety:

1. **Global Charts** (50%) - Most popular songs worldwide
2. **Weekly Charts** (25%) - Trending songs this week
3. **Persian Charts** (25%) - Iranian/Persian music

## Rate Limits

The system respects API rate limits:

| API                | Limit         | Usage per Run | Safe? |
|--------------------|---------------|---------------|-------|
| Deezer             | ~50 req/min   | 3-5 requests  | ✅    |
| MusicBrainz        | 60 req/min    | 15 requests   | ✅    |
| Last.fm            | 300 req/min   | 15 requests   | ✅    |
| Librosa (CPU)      | ~3-5 sec/song | 15 songs      | ✅    |

**Total time per run**: ~60-90 seconds (runs in background, doesn't block bot)

## Storage

### Database Size Estimates

```
Songs per day:     24 × 60 × 15 = 21,600 songs
Songs per month:   21,600 × 30 = 648,000 songs

Storage per song:
- Audio features:    ~2 KB
- Acoustic features: ~1 KB
- Metadata:          ~0.5 KB
- Total:             ~3.5 KB per song

Total storage/month: 648,000 × 3.5 KB ≈ 2.3 GB
```

### Automatic Cleanup

The scheduler automatically removes entries older than 30 days:
- Runs daily at 3 AM
- Can be run manually: `python prefetch_popular.py --cleanup`
- Configurable: `python prefetch_popular.py --cleanup-days 60`

## Monitoring

### View Logs

```bash
# Real-time prefetch logs
tail -f prefetch.log

# Bot logs include prefetch info
tail -f bot.log | grep PREFETCH
```

### Check Statistics

```bash
# Quick stats
python prefetch_popular.py --stats

# Example output:
# === Cache Statistics ===
# Total songs: 15,432
# With audio features: 14,891
# With acoustic features: 12,345
# With MusicBrainz ID: 13,678
# With Last.fm tags: 11,234
# Last 24h: 21,600
# Last 7 days: 151,200
# ========================
```

### Database Inspection

```bash
# Open SQLite database
sqlite3 feature_cache.db

# View table structure
.schema track_features

# Count cached songs
SELECT COUNT(*) FROM track_features;

# View recent additions
SELECT title, artist, analyzed_at
FROM track_features
ORDER BY analyzed_at DESC
LIMIT 10;

# Check cache hit rate (requires bot logging)
grep "Cache HIT" bot.log | wc -l
grep "Cache MISS" bot.log | wc -l
```

## Performance Benefits

### Before Prefetch

```
User searches "Bohemian Rhapsody"
→ Deezer API: 0.5s
→ Download preview: 1s
→ Librosa analysis: 5s
→ MusicBrainz API: 2s
→ AcousticBrainz API: 2s
→ Last.fm API: 0.5s
→ Total: ~11 seconds
```

### After Prefetch

```
User searches "Bohemian Rhapsody"
→ Check cache: 0.001s
→ Return cached features: 0.001s
→ Total: ~0.002 seconds (5500x faster!)
```

## Troubleshooting

### Issue: Prefetch not running

**Check logs:**
```bash
grep "SCHEDULER" bot.log
```

**Common causes:**
1. `ENABLE_PREFETCH=false` in `.env`
2. Import error in `prefetch_popular.py`
3. API credentials missing

**Solution:**
```bash
# Test prefetch manually
python prefetch_popular.py --target 5

# Check for errors
python -c "from prefetch_popular import run_prefetch; import asyncio; asyncio.run(run_prefetch(5))"
```

### Issue: High API usage

**Symptoms:**
- 429 errors in logs
- Slow prefetch runs

**Solution:**
```python
# Reduce target in prefetch_popular.py
TARGET_SONGS_PER_RUN = 10  # Down from 15

# Or increase interval in bot.py scheduler
time.sleep(120)  # Every 2 minutes instead of 1
```

### Issue: Large database size

**Check size:**
```bash
ls -lh feature_cache.db
```

**Solution:**
```bash
# Run aggressive cleanup
python prefetch_popular.py --cleanup --cleanup-days 14

# Or vacuum database
sqlite3 feature_cache.db "VACUUM;"
```

### Issue: Cache misses for popular songs

**Cause:** Songs not in charts, or charts changed

**Solution:**
```python
# Add seed list of popular songs
SEED_SONGS = [
    "Bohemian Rhapsody Queen",
    "Hotel California Eagles",
    # ... add more
]

# Modify get_popular_songs() to include seed list
```

## Advanced Usage

### Custom Genre Prefetching

Add support for specific genres:

```python
# In prefetch_popular.py
GENRE_IDS = {
    "pop": 132,
    "rock": 152,
    "hip_hop": 116,
    "electronic": 106,
    "persian": 196,
    "arabic": 165,
}

async def prefetch_by_genre(genre_name: str, limit: int = 10):
    genre_id = GENRE_IDS.get(genre_name)
    if not genre_id:
        raise ValueError(f"Unknown genre: {genre_name}")

    dz = DeezerClient()
    tracks = await dz.get_genre_charts(genre_id, limit)
    # ... prefetch tracks
```

### Priority Prefetching

Prefetch songs before major events:

```python
# Prefetch Grammy nominations
async def prefetch_award_nominations():
    nominees = [
        "Song of the Year nominee 1",
        "Song of the Year nominee 2",
        # ...
    ]
    dz = DeezerClient()
    for song in nominees:
        tracks = await dz.search(song, limit=1)
        if tracks:
            await prefetch_song(tracks[0], ...)
```

### Export to JSON

Export cached data for analysis:

```bash
# Export all cached songs to JSON
python -c "
import asyncio
from feature_cache import export_cache_to_json
asyncio.run(export_cache_to_json('cached_songs_export.json'))
"

# Analyze with jq
cat cached_songs_export.json | jq '.[] | {title, artist, bpm, energy}'
```

## Architecture Decisions

### Why SQLite?

- **Single file**: Easy to backup and deploy
- **No server**: Runs anywhere Python runs
- **ACID**: Safe concurrent reads/writes
- **Performance**: Handles 100K+ songs easily

### Why 15 songs per minute?

- **Deezer**: ~50 req/min safe limit, using 3-5
- **MusicBrainz**: 60 req/min, using 15
- **Last.fm**: 300 req/min, using 15
- **Librosa**: ~3-5 sec/song = 45-75 sec total
- **Balance**: Maximize cache growth without hitting limits

### Why 30-day cleanup?

- **Storage**: Keeps database under 3GB
- **Relevance**: Old songs less likely to be requested
- **Freshness**: Charts change, so should cache

## Future Improvements

### Short-term (1-2 weeks)

1. **User-driven prefetch**: When user searches a song, prefetch similar songs
2. **Genre balancing**: Ensure diverse genres in cache
3. **Priority queue**: Prefetch songs requested by multiple users

### Medium-term (1-2 months)

1. **Redis cache**: Move hot songs to Redis for faster access
2. **CDN integration**: Cache preview MP3s on CDN
3. **Machine learning**: Predict which songs will be popular

### Long-term (3-6 months)

1. **Distributed prefetch**: Run multiple prefetch workers
2. **Real-time updates**: WebSocket notifications when new songs cached
3. **A/B testing**: Test different prefetch strategies

## Contributing

To improve the prefetch system:

1. **Add new data sources**: Spotify charts, Apple Music top songs
2. **Optimize analysis**: Faster librosa alternatives
3. **Better deduplication**: Semantic similarity detection
4. **Smart scheduling**: Adjust rate based on bot load

## Support

For issues or questions:

1. Check logs: `tail -f prefetch.log`
2. Test manually: `python prefetch_popular.py --target 5`
3. Check stats: `python prefetch_popular.py --stats`
4. Open GitHub issue with logs attached

---

**Last Updated**: 2026-08-07
**Version**: 1.0.0
